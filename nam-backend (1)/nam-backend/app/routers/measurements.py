"""Measurement suite at Mars Trek parity: 12 tools, each result states its
data source and resolution in the response (Phase 1 gate requirement)."""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import routing, terrain
from ..integrity import with_sim
from ..mars import hav_km, poly_area_km2, sun_geometry

router = APIRouter(prefix="/measure", tags=["measurements"])
T = terrain.engine()


def _pts(points):
    out = []
    for p in points:
        if isinstance(p, dict):
            out.append({"lat": float(p["lat"]), "lon": float(p["lon"])})
        else:
            out.append({"lat": float(p[0]), "lon": float(p[1])})
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
    res = routing.plan_route(r.from_lat, r.from_lon, r.to_lat, r.to_lon, r.preset)
    if res.get("stats") is None:
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
    a, b = c.rim_a, c.rim_b
    d = hav_km(a["lat"], a["lon"], b["lat"], b["lon"])
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
            "method": "spherical shoelace on local ellipsoid radius",
            "provenance": {"source": "NAM geodesy", "resolution": "n/a"}}


# 7. slope at a point (regional variant under /terrain/hazard)
@router.get("/slope")
def slope_at(lat: float, lon: float):
    return {"tool": "slope_at_point", "lat": lat, "lon": lon,
            "slope_deg": round(T.ensure().slope(lat, lon), 2),
            "provenance": T.prov()}


# 8. elevation difference
class TwoPts(BaseModel):
    a: dict
    b: dict


@router.post("/elevation_difference")
def elevation_difference(t: TwoPts):
    ea = T.ensure().elev(t.a["lat"], t.a["lon"])
    eb = T.elev(t.b["lat"], t.b["lon"])
    return {"tool": "elevation_difference", "a_elev_m": round(ea, 1), "b_elev_m": round(eb, 1),
            "difference_m": round(eb - ea, 1), "provenance": T.prov()}


# 9. solar illumination angles
@router.post("/solar")
def solar(s: SolarIn):
    out = sun_geometry(s.lat, s.lon, s.iso_time, s.ls_deg, s.slope_deg, s.azimuth_deg)
    out["tool"] = "solar_illumination"
    return out


# 10. raw terrain download
@router.get("/terrain_download")
def terrain_download(min_lat: float, min_lon: float, max_lat: float, max_lon: float):
    st = T.ensure().bbox_stats((min_lat, min_lon, max_lat, max_lon))
    body = json.dumps({"bbox_stats": st, "format": "request /terrain/patch or /terrain/mesh "
                       "for the grid arrays; production serves MOLA MEGDR npz/geotiff",
                       "provenance": T.prov()}, indent=1).encode()
    return Response(content=body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="nam_terrain_stats.json"'})


# 12. 3D-printable STL export
@router.post("/stl")
def stl_export(s: StlIn):
    data = T.ensure().stl_bytes(s.lat, s.lon, s.radius_km, s.vertical_scale, s.n)
    hdr = ("NAM terrain export [SIM]: demo grid + procedural detail; "
           "vertical scale x%.1f; patch %.0f km around (%.2f, %.2f)"
           % (s.vertical_scale, s.radius_km, s.lat, s.lon))
    return Response(
        content=data, media_type="model/stl",
        headers={"Content-Disposition": 'attachment; filename="nam_terrain.stl"',
                 "X-NAM-Vertical-Scale": str(s.vertical_scale),
                 "X-NAM-Provenance": hdr})
