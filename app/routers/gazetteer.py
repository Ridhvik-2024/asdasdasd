"""Gazetteer search, location cards, bookmarks, share links, landing sites."""
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db, seeds, terrain
from ..integrity import prov
from ..mars import hav_km, validate_coords, validate_lat, validate_lon

router = APIRouter(tags=["gazetteer"])


@router.get("/search")
def search(q: str, type: str = None, limit: int = 12):
    t0 = time.perf_counter()
    if len(q) > 200 or not q.strip():
        raise HTTPException(400, "Enter a search query of 1–200 characters")
    try:
        res = seeds.search(q, type_=type, limit=max(1, min(limit, 100)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return {"query": q, "count": len(res), "latency_ms": ms, "results": res,
            "provenance": prov(source="USGS Gazetteer of Planetary Nomenclature + NAM curated features + mission landing sites",
                               url="https://planetarynames.wr.usgs.gov/",
                               note="fuzzy search target: <300 ms (Phase 1 gate)")}


@router.get("/landing_sites")
def landing_sites():
    sites = seeds.landing_sites()
    T = terrain.engine().ensure()
    for s in sites:
        s["elevation_m"] = round(T.elev(s["lat"], s["lon"]), 1)
        s["rover_imagery"] = bool(seeds.rover_region(s["lat"], s["lon"]))
    return {"count": len(sites), "sites": sites,
            "provenance": prov(source="NASA/JPL/CNSA published landing coordinates",
                               note="all successful Mars missions as first-class search results")}


def _imagery_depth(lat, lon):
    for inset in seeds.hirise_insets():
        if hav_km(lat, lon, inset["lat"], inset["lon"]) < 25:
            return {"deepest_layer": "HiRISE (~0.3 m/px inset)", "inset": inset["name"],
                    "ladder": ["HiRISE 0.3 m/px", "CTX Murray 5 m/px", "MDIM 2.1 232 m/px"]}
    return {"deepest_layer": "CTX Murray mosaic (5 m/px)",
            "ladder": ["CTX Murray 5 m/px", "MDIM 2.1 232 m/px"]}


@router.get("/location/card")
def location_card_coords(lat: float, lon: float):
    try:
        vlat, vlon = validate_coords(lat, lon)
    except ValueError as e:
        raise HTTPException(400, str(e))
    T = terrain.engine().ensure()
    elev = round(T.elev(vlat, vlon), 1)
    slope = round(T.slope(vlat, vlon), 2)
    aspect = round(T.aspect(vlat, vlon), 1)
    nearby = seeds.nearest(vlat, vlon, radius_km=350, limit=8)
    obs = seeds.observations(lat=vlat, lon=vlon, radius_km=500, limit=8)
    pans = seeds.panoramas_near(vlat, vlon, radius_km=150)
    region = seeds.region_context(vlat, vlon)
    depth = _imagery_depth(vlat, vlon)
    return {
        "lat": vlat, "lon": vlon,
        "terrain": {"elevation_m": elev, "slope_deg": slope, "aspect_deg": aspect},
        "region_context": region,
        "imagery_depth": {
            "best_available": depth["deepest_layer"],
            "hirise_inset": "inset" in depth,
            "ladder": depth["ladder"],
        },
        "nearby_features": nearby,
        "observations": obs,
        "nearest_panoramas": pans[:6],
        "provenance": {"elevation": T.prov(), "gazetteer": prov("USGS Gazetteer of Planetary Nomenclature")},
    }


@router.get("/locations/{fid}")
def location_card(fid: str):
    f = seeds.by_id(fid)
    if not f:
        raise HTTPException(404, "unknown location id")
    T = terrain.engine().ensure()
    lat, lon = f["lat"], f["lon"]
    elev = round(T.elev(lat, lon), 1)
    slope = round(T.slope(lat, lon), 2)
    nearby = seeds.nearest(lat, lon, radius_km=300, limit=8)
    obs = seeds.observations(lat=lat, lon=lon, radius_km=400, limit=8)
    pans = seeds.panoramas_near(lat, lon, radius_km=150)
    region = seeds.region_context(lat, lon)
    region_rover = seeds.rover_region(lat, lon)
    card = {
        "id": f["id"], "name": f["name"], "type": f.get("type"), "lat": lat, "lon": lon,
        "diameter_km": f.get("diameter_km"), "note": f.get("note"),
        "elevation_m": elev, "slope_deg": slope,
        "geologic_context": region,
        "nearby_features": nearby,
        "nearby_observations": [{"id": o["id"], "title": o["title"], "instrument": o["instrument"],
                                 "evidence": o["evidence"], "distance_km": o.get("distance_km")}
                                for o in obs],
        "imagery_depth": _imagery_depth(lat, lon),
        "rover_imagery": {"available": bool(region_rover or pans),
                          "region": region_rover, "panorama_count": len(pans)}
        if (region_rover or pans) else {"available": False},
        "provenance": {
            "feature": prov(source=f.get("src") or "USGS Gazetteer of Planetary Nomenclature",
                            url=f.get("url")),
            "elevation": T.prov(),
        },
    }
    return card


class BookmarkIn(BaseModel):
    name: str
    lat: float
    lon: float
    camera: dict = {}


@router.post("/bookmarks")
def add_bookmark(b: BookmarkIn):
    try:
        vlat, vlon = validate_coords(b.lat, b.lon)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with db.tx():
        bid = db.ex("INSERT INTO bookmarks (name,lat,lon,camera_json) VALUES (?,?,?,?)",
                    (b.name, vlat, vlon, db.j(b.camera)))
        rows = db.q("SELECT * FROM bookmarks WHERE id=?", (bid,))
    return rows[0] | {"camera": b.camera}


@router.get("/bookmarks")
def list_bookmarks():
    rows = db.q("SELECT * FROM bookmarks ORDER BY id DESC")
    return [{"id": r["id"], "name": r["name"], "lat": r["lat"], "lon": r["lon"],
             "camera": db.uj(r["camera_json"], {})} for r in rows]


@router.delete("/bookmarks/{bid}")
def del_bookmark(bid: int):
    if db.ex_count("DELETE FROM bookmarks WHERE id=?", (bid,)) == 0:
        raise HTTPException(404, "unknown bookmark")
    return {"deleted": bid}


class ShareIn(BaseModel):
    name: str = ""
    camera: dict


@router.post("/share")
def share(s: ShareIn):
    try:
        if "lat" in s.camera and s.camera["lat"] is not None:
            validate_lat(s.camera["lat"])
        if "lon" in s.camera and s.camera["lon"] is not None:
            validate_lon(s.camera["lon"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    sid = uuid.uuid4().hex[:10]
    payload = {"name": s.name, "camera": s.camera}
    db.ex("INSERT INTO share_links (id,payload_json) VALUES (?,?)", (sid, db.j(payload)))
    return {"share_id": sid, "url": "/share/" + sid, "payload": payload,
            "note": "link encodes camera state (lat, lon, height, heading, layers)"}


@router.get("/share/{sid}")
def get_share(sid: str):
    rows = db.q("SELECT * FROM share_links WHERE id=?", (sid,))
    if not rows:
        raise HTTPException(404, "unknown share link")
    return db.uj(rows[0]["payload_json"], {})
