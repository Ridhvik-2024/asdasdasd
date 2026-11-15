"""Scientific explorer: layer registry, discovery browser, landing-site compare."""
import math
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import resources, seeds, terrain
from ..integrity import prov
from ..mars import hav_km, validate_coords, validate_lat, validate_lon

router = APIRouter(tags=["science"])
T = terrain.engine()


@router.get("/layers")
def layers_list(category: str = None):
    out = seeds.layers()
    if category:
        out = [l for l in out if l["category"] == category]
    return {"count": len(out), "layers": out,
            "provenance": prov(source="NAM science layer registry",
                               note="every layer carries legend, metadata and source id")}


@router.get("/layers/{lid}")
def layer_get(lid: str):
    l = seeds.layer(lid)
    if not l:
        raise HTTPException(404, "unknown layer")
    return {"layer": l, "provenance": prov(source=l["source"], url=l.get("url"),
                                           attribution=l.get("attribution"))}


class LayerCompare(BaseModel):
    layer_a: str
    layer_b: str
    bbox: Optional[list] = None


@router.post("/layers/compare")
def layers_compare(c: LayerCompare):
    a, b = seeds.layer(c.layer_a), seeds.layer(c.layer_b)
    if not a or not b:
        raise HTTPException(404, "unknown layer id")
    stats = None
    if c.bbox is not None:
        if len(c.bbox) != 4:
            raise HTTPException(400, "bbox must have 4 elements [min_lat, min_lon, max_lat, max_lon]")
        try:
            min_lat = validate_lat(c.bbox[0])
            min_lon = validate_lon(c.bbox[1])
            max_lat = validate_lat(c.bbox[2])
            max_lon = validate_lon(c.bbox[3])
        except ValueError as e:
            raise HTTPException(400, str(e))
        stats = T.ensure().bbox_stats((min_lat, min_lon, max_lat, max_lon))
    return {"layer_a": a, "layer_b": b, "bbox_stats": stats,
            "comparison_note": "layers share the same layer/picking/measurement state across all views",
            "provenance": prov(source="NAM layer comparison", note="compare_geological_layers tool backend")}


@router.get("/discoveries")
def discoveries(q: str = None, instrument: str = None, lat: float = None, lon: float = None,
                radius_km: float = 400, limit: int = 20):
    vlat, vlon = None, None
    if lat is not None or lon is not None:
        try:
            if lat is not None:
                validate_lat(lat)
            if lon is not None:
                validate_lon(lon)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if lat is None or lon is None:
            raise HTTPException(400, "provide both lat and lon for proximity search")
        vlat, vlon = validate_coords(lat, lon)
    if not math.isfinite(radius_km) or radius_km <= 0.0:
        raise HTTPException(400, "radius_km must be a positive finite number")
    obs = seeds.observations(q=q, instrument=instrument, lat=vlat, lon=vlon,
                             radius_km=radius_km, limit=limit)
    return {"count": len(obs), "discoveries": obs,
            "provenance": prov(source="peer-reviewed publications + NASA mission pages (per-card citations)",
                               note="every card shows observation, source and coordinates")}


@router.get("/discoveries/{oid}")
def discovery(oid: str):
    o = seeds.observation(oid)
    if not o:
        raise HTTPException(404, "unknown discovery")
    return {"discovery": o, "provenance": o.get("evidence", {})}


@router.get("/sites")
def sites_list():
    return {"sites": seeds.landing_sites()}


@router.get("/sites/compare")
def sites_compare(ids: str, ids2: str = None):
    wanted = [x.strip() for x in ids.split(",")] + ([ids2] if ids2 else [])
    out = []
    T.ensure()
    for sid in wanted[:3]:
        site = next((s for s in seeds.landing_sites() if s["id"] == sid), None)
        if not site:
            raise HTTPException(404, "unknown site: %s" % sid)
        st = T.bbox_stats((site["lat"] - 0.5, site["lon"] - 0.5, site["lat"] + 0.5, site["lon"] + 0.5))
        water = resources.find_water(near={"lat": site["lat"], "lon": site["lon"]}, radius_km=1500)
        obs = seeds.observations(lat=site["lat"], lon=site["lon"], radius_km=500, limit=6)
        pans = seeds.panoramas_near(site["lat"], site["lon"], radius_km=60)
        out.append({
            "id": site["id"], "name": site["name"], "mission": site["mission"],
            "lat": site["lat"], "lon": site["lon"], "landing_date": site["date"],
            "elevation_m": round(T.elev(site["lat"], site["lon"]), 1),
            "local_terrain": st,
            "water_candidates_within_1500km": len(water),
            "nearest_water": (water[0] if water else None),
            "cited_discoveries": len(obs),
            "top_discovery": (obs[0] if obs else None),
            "panoramas_available": len(pans),
        })
    return {"comparison": out,
            "provenance": prov(source="NAM landing-site comparison (terrain stats [SIM] from demo grid)")}


@router.get("/datasets")
def datasets_list(q: str = None, org: str = None):
    items = seeds.datasets()
    if org:
        items = [d for d in items if org.lower() in (d.get("org") or "").lower()]
    if q:
        ql = q.lower()
        items = [d for d in items if ql in (d["name"] + " " + d["org"] + " " + d["note"]).lower()]
    return {
        "count": len(items),
        "datasets": items,
        "provenance": prov("NASA PDS / USGS Astrogeology / Caltech Murray Lab / ESA dataset registry"),
    }


@router.get("/science/orbiters")
def science_orbiters(status: str = None):
    items = seeds.orbiters()
    if status:
        items = [o for o in items if status.lower() in (o.get("status") or "").lower()]
    return {
        "count": len(items),
        "orbiters": items,
        "provenance": prov("NASA PDS / ESA PSA / UAESA / CNSA published orbiter mission records"),
    }


@router.get("/science/instruments")
def science_instruments(q: str = None, mission: str = None):
    items = seeds.instruments(q=q, mission=mission)
    return {
        "count": len(items),
        "instruments": items,
        "provenance": prov("NASA PDS / ESA / mission instrument handbooks"),
    }


@router.get("/science/spectral_targets")
def science_spectral_targets(q: str = None, mineral: str = None,
                             lat: float = None, lon: float = None,
                             radius_km: float = 600):
    vlat, vlon = None, None
    if lat is not None or lon is not None:
        if lat is None or lon is None:
            raise HTTPException(400, "provide both lat and lon for proximity search")
        try:
            vlat, vlon = validate_coords(lat, lon)
        except ValueError as e:
            raise HTTPException(400, str(e))
    if not math.isfinite(radius_km) or radius_km <= 0.0:
        raise HTTPException(400, "radius_km must be > 0")
    items = seeds.spectral_targets(q=q, mineral=mineral, lat=vlat, lon=vlon, radius_km=radius_km)
    return {
        "count": len(items),
        "spectral_targets": items,
        "provenance": prov("Peer-reviewed CRISM / OMEGA / TES / THEMIS / SHARAD mineralogical publications"),
    }


@router.get("/science/unavailable_sources")
def science_unavailable_sources():
    items = seeds.unavailable_sources()
    return {
        "count": len(items),
        "unavailable_sources": items,
        "note": "Honest degradation: these external services are not faked; official access paths are listed.",
        "provenance": prov("NAM integrity & service-boundary registry"),
    }


@router.get("/science/catalog")
def science_catalog():
    return {
        "counts": {
            "landing_sites": len(seeds.landing_sites()),
            "orbiters": len(seeds.orbiters()),
            "instruments": len(seeds.instruments()),
            "spectral_targets": len(seeds.spectral_targets()),
            "observations": len(seeds.observations(limit=500)),
            "layers": len(seeds.layers()),
            "datasets": len(seeds.datasets()),
            "unavailable_sources": len(seeds.unavailable_sources()),
        },
        "provenance": prov("NAM v2 Scientific Database catalog summary"),
    }

