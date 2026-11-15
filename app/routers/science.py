"""Scientific explorer: layer registry, discovery browser, landing-site compare."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import resources, seeds, terrain
from ..integrity import prov
from ..mars import hav_km

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
    bbox: list = None


@router.post("/layers/compare")
def layers_compare(c: LayerCompare):
    a, b = seeds.layer(c.layer_a), seeds.layer(c.layer_b)
    if not a or not b:
        raise HTTPException(404, "unknown layer id")
    stats = None
    if c.bbox and len(c.bbox) == 4:
        stats = T.ensure().bbox_stats(tuple(c.bbox))
    return {"layer_a": a, "layer_b": b, "bbox_stats": stats,
            "comparison_note": "layers share the same layer/picking/measurement state across all views",
            "provenance": prov(source="NAM layer comparison", note="compare_geological_layers tool backend")}


@router.get("/discoveries")
def discoveries(q: str = None, instrument: str = None, lat: float = None, lon: float = None,
                radius_km: float = 400, limit: int = 20):
    obs = seeds.observations(q=q, instrument=instrument, lat=lat, lon=lon,
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
