"""Measurement suite at Mars Trek parity: 12 tools, each result states its
data source and resolution in the response (Phase 1 gate requirement)."""
import csv
import io
import json
import math

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import numpy as np
from pydantic import BaseModel

from .. import routing, terrain
from ..integrity import with_sim
from ..mars import hav_km, poly_area_km2, sun_geometry, validate_coords, validate_lat, validate_lon

router = APIRouter(prefix="/measure", tags=["measurements"])
T = terrain.engine()


def _check_coords(lat, lon):
    try:
        return validate_coords(lat, lon)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _pts(points):
    out = []
    for p in points:
        if isinstance(p, dict):
            vlat, vlon = _check_coords(p["lat"], p["lon"])
        else:
            vlat, vlon = _check_coords(p[0], p[1])
        out.append({"lat": vlat, "lon": vlon})
    return out


class PointsIn(BaseModel):
    points: list


class CraterIn(BaseModel):
    rim_a: dict
    rim_b: dict


class SolarIn(BaseModel):
    lat: float
    lon: float
    iso_time: str
    ls_deg: float = None
    slope_deg: float = None
    azimuth_deg: float = None


class StlIn(BaseModel):
    lat: float
    lon: float
    radius_km: float = 20.0
    vertical_scale: float = 5.0
    n: int = 96


# 1. straight-line distance
@router.post("/distance")
def distance(p: PointsIn):
    pts = _pts(p.points)
    if len(pts) < 2:
        raise HTTPException(400, "need >= 2 points")
    total = sum(hav_km(pts[i]["lat"], pts[i]["lon"], pts[i + 1]["lat"], pts[i + 1]["lon"])
                for i in range(len(pts) - 1))
    return {"tool": "straight_line_distance", "distance_km": round(total, 4),
            "method": "haversine on IAU-ellipsoid local radius",
            "provenance": {"source": "NAM geodesy (IAU Mars ellipsoid)", "resolution": "n/a"}}


# 2. path distance (polyline, same as above but labelled for path tooling)
@router.post("/path_distance")
def path_distance(p: PointsIn):
    r = distance(p)
    r["tool"] = "path_distance"
    return r


# 3. route distance over terrain (A*)
class RouteIn(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    preset: str = "balanced"


@router.post("/route_distance")
def route_distance(r: RouteIn):
    try:
        res = routing.plan_route(r.from_lat, r.from_lon, r.to_lat, r.to_lon, r.preset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if res.get("status") == "degraded" or not res.get("stats") or res["stats"].get("length_km") is None:
        return with_sim(res, note="routing degraded; straight-line fallback")
    return {"tool": "route_distance", **res["stats"], "path_preview": res["path"][:: max(1, len(res["path"]) // 20)],
            "provenance": res["provenance"]}


# 4. elevation profile (also returns cross-section stats: tool 11)
@router.post("/profile")
def profile(p: PointsIn, samples: int = 180):
    pts = _pts(p.points)
    if len(pts) < 2:
        raise HTTPException(400, "need >= 2 points")
    prof = T.ensure().profile(pts, samples=samples)
    prof["tool"] = "elevation_profile"
    prof["cross_section"] = {"min_m": prof["min_elev_m"], "max_m": prof["max_elev_m"],
                             "gain_m": prof["elevation_gain_m"], "loss_m": prof["elevation_loss_m"]}
    return prof


# 5. crater diameter + derived depth
@router.post("/crater")
def crater(c: CraterIn):
    alat, alon = _check_coords(c.rim_a["lat"], c.rim_a["lon"])
    blat, blon = _check_coords(c.rim_b["lat"], c.rim_b["lon"])
    d = hav_km(alat, alon, blat, blon)
    est = T.ensure().crater_depth(d)
    return {"tool": "crater_diameter", "diameter_km": round(d, 3), **est}


# 6. surface area
class PolyIn(BaseModel):
    polygon: list


@router.post("/area")
def area(p: PolyIn):
    pts = _pts(p.polygon)
    if len(pts) < 3:
        raise HTTPException(400, "need >= 3 polygon points")
    return {"tool": "surface_area", "area_km2": round(poly_area_km2(pts), 4),
            "method": "exact spherical geodesic excess on IAU Mars ellipsoid",
            "provenance": {"source": "NAM geodesy", "resolution": "n/a"}}


# 7. slope at a point (regional variant under /terrain/hazard)
@router.get("/slope")
def slope_at(lat: float, lon: float):
    vlat, vlon = _check_coords(lat, lon)
    return {"tool": "slope_at_point", "lat": lat, "lon": vlon,
            "slope_deg": round(T.ensure().slope(vlat, vlon), 2),
            "provenance": T.prov()}


# 8. elevation difference
class TwoPts(BaseModel):
    a: dict
    b: dict


@router.post("/elevation_difference")
def elevation_difference(t: TwoPts):
    alat, alon = _check_coords(t.a["lat"], t.a["lon"])
    blat, blon = _check_coords(t.b["lat"], t.b["lon"])
    ea = T.ensure().elev(alat, alon)
    eb = T.elev(blat, blon)
    return {"tool": "elevation_difference", "a_elev_m": round(ea, 1), "b_elev_m": round(eb, 1),
            "difference_m": round(eb - ea, 1), "provenance": T.prov()}


# 9. solar illumination angles
@router.post("/solar")
def solar(s: SolarIn):
    try:
        out = sun_geometry(s.lat, s.lon, s.iso_time, s.ls_deg, s.slope_deg, s.azimuth_deg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    out["tool"] = "solar_illumination"
    return out


# 10. terrain dataset download (json grid+stats | csv | npz | obj)
@router.get("/terrain_download")
def terrain_download(min_lat: float, min_lon: float, max_lat: float, max_lon: float,
                     format: str = "json"):
    try:
        validate_lat(min_lat); validate_lat(max_lat)
        validate_lon(min_lon); validate_lon(max_lon)
    except ValueError as e:
        raise HTTPException(400, str(e))
    exp = T.ensure().export_bbox((min_lat, min_lon, max_lat, max_lon))
    fmt = (format or "json").lower()
    if fmt == "json":
        body = json.dumps(exp, indent=1).encode("utf-8")
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="nam_terrain_grid.json"',
                                 "X-NAM-Provenance": exp["provenance"]["source"]})
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["lat", "lon", "elevation_m"])
        for lat_v, row in zip(exp["lats"], exp["elevation_m"]):
            for lon_v, elev_v in zip(exp["lons"], row):
                writer.writerow([lat_v, lon_v, elev_v])
        return Response(content=buf.getvalue().encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="nam_terrain_grid.csv"',
                                 "X-NAM-Provenance": exp["provenance"]["source"]})
    if fmt == "npz":
        bio = io.BytesIO()
        np.savez_compressed(
            bio,
            lats=np.array(exp["lats"], dtype=np.float64),
            lons=np.array(exp["lons"], dtype=np.float64),
            elevation_m=np.array(exp["elevation_m"], dtype=np.float64),
            crs=np.array(exp["crs"]),
            provenance=np.array(json.dumps(exp["provenance"])),
        )
        return Response(content=bio.getvalue(), media_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="nam_terrain_grid.npz"',
                                 "X-NAM-Provenance": exp["provenance"]["source"]})
    if fmt == "obj":
        lines = ["# NAM Mars terrain mesh export [SIM]", "# CRS: %s" % exp["crs"]]
        lats_a, lons_a, elev_a = exp["lats"], exp["lons"], exp["elevation_m"]
        nr, nc = len(lats_a), len(lons_a)
        for i in range(nr):
            for j in range(nc):
                lines.append("v %.5f %.5f %.2f" % (lons_a[j], lats_a[i], elev_a[i][j]))
        for i in range(nr - 1):
            for j in range(nc - 1):
                a = i * nc + j + 1; b = a + 1; c = a + nc; d = c + 1
                lines.append("f %d %d %d" % (a, b, c))
                lines.append("f %d %d %d" % (b, d, c))
        return Response(content=("\n".join(lines) + "\n").encode("utf-8"), media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="nam_terrain.obj"',
                                 "X-NAM-Provenance": exp["provenance"]["source"]})
    raise HTTPException(400, "unsupported format (use json|csv|npz|obj)")


# 12. 3D-printable STL export
@router.post("/stl")
def stl_export(s: StlIn):
    vlat, vlon = _check_coords(s.lat, s.lon)
    if not math.isfinite(s.radius_km) or s.radius_km <= 0 or not math.isfinite(s.vertical_scale) or s.vertical_scale <= 0:
        raise HTTPException(400, "radius_km and vertical_scale must be > 0")
    data = T.ensure().stl_bytes(vlat, vlon, s.radius_km, s.vertical_scale, s.n)
    hdr = ("NAM terrain export [SIM]: demo grid + procedural detail; "
           "vertical scale x%.1f; patch %.0f km around (%.2f, %.2f)"
           % (s.vertical_scale, s.radius_km, vlat, vlon))
    return Response(
        content=data, media_type="model/stl",
        headers={"Content-Disposition": 'attachment; filename="nam_terrain.stl"',
                 "X-NAM-Vertical-Scale": str(s.vertical_scale),
                 "X-NAM-Provenance": hdr})
