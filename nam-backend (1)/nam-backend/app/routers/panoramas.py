"""Mars Street View backend: panorama catalogue, camera poses, traverses,
orbital-to-ground linkage, historical imagery timelines."""
from fastapi import APIRouter, HTTPException

from .. import seeds
from ..integrity import prov
from ..mars import bearing, hav_km

router = APIRouter(tags=["streetview"])


@router.get("/panoramas")
def panorama_list(rover: str = None):
    ps = seeds.panoramas()
    if rover:
        ps = [p for p in ps if p["rover"].lower() == rover.lower()]
    return {"count": len(ps), "panoramas": ps,
            "provenance": prov(source="NASA/JPL-published panoramas (credits per item)",
                               note="asset IDs verified at connector time; source page always shown")}


@router.get("/panoramas/near")
def panorama_near(lat: float, lon: float, radius_km: float = 50):
    ps = seeds.panoramas_near(lat, lon, radius_km)
    return {"count": len(ps), "panoramas": ps,
            "provenance": prov(source="NAM panorama catalogue (NASA/JPL credits)")}


@router.get("/panoramas/{pid}")
def panorama_get(pid: str):
    p = seeds.panorama(pid)
    if not p:
        raise HTTPException(404, "unknown panorama")
    neighbors = traverse_neighbors(pid)
    return {"panorama": p, "adjacent_observation_points": neighbors["adjacent"],
            "provenance": {"credit": p["credit"], "source_url": p["source_url"],
                           "pose_confidence": p["pose_confidence"]}}


@router.get("/panoramas/{pid}/neighbors")
def traverse_neighbors(pid: str):
    p = seeds.panorama(pid)
    if not p:
        raise HTTPException(404, "unknown panorama")
    pts = seeds.traverse(p["rover"])
    i = next((k for k, x in enumerate(pts) if x["id"] == pid), None)
    adj = []
    if i is not None:
        if i > 0:
            adj.append({"id": pts[i - 1]["id"], "title": pts[i - 1]["title"],
                        "bearing_deg": round(bearing(p["lat"], p["lon"], pts[i - 1]["lat"], pts[i - 1]["lon"]), 1),
                        "distance_km": round(hav_km(p["lat"], p["lon"], pts[i - 1]["lat"], pts[i - 1]["lon"]), 2)})
        if i < len(pts) - 1:
            adj.append({"id": pts[i + 1]["id"], "title": pts[i + 1]["title"],
                        "bearing_deg": round(bearing(p["lat"], p["lon"], pts[i + 1]["lat"], pts[i + 1]["lon"]), 1),
                        "distance_km": round(hav_km(p["lat"], p["lon"], pts[i + 1]["lat"], pts[i + 1]["lon"]), 2)})
    return {"rover": p["rover"], "adjacent": adj,
            "note": "walking the traverse navigates between adjacent observation points"}


@router.get("/traverses")
def traverse_list():
    rovers = sorted({p["rover"] for p in seeds.panoramas()})
    return {"rovers": [{"rover": r, "points": len(seeds.traverse(r))} for r in rovers],
            "provenance": prov(source="published traverse sequences in panorama catalogue")}


@router.get("/traverses/{rover}")
def traverse_get(rover: str):
    pts = seeds.traverse(rover)
    if not pts:
        raise HTTPException(404, "no traverse for rover")
    return {"rover": rover, "points": pts,
            "note": "ordered by sol; clickable camera markers with pose, date and credit"}


@router.get("/imagery/linkage")
def imagery_linkage(lat: float, lon: float):
    """Orbital-to-ground linkage both ways: from a globe point, the imagery
    footprint and the nearest ground photographs."""
    region = seeds.rover_region(lat, lon)
    near = seeds.panoramas_near(lat, lon, radius_km=80)
    return {"lat": lat, "lon": lon,
            "footprint": {"deepest_layer": "CTX Murray (5 m/px)",
                          "hiRISE_inset_available": any(
                              hav_km(lat, lon, h["lat"], h["lon"]) < 25
                              for h in seeds.hirise_insets())},
            "nearest_ground_photographs": near[:6],
            "rover_region": region,
            "link_back": "from inside a panorama the inset map shows view bearing and links to this orbital view",
            "provenance": prov(source="NAM orbital-to-ground linkage (panorama catalogue)")}


@router.get("/sites/{rover}/timeline")
def timeline(rover: str):
    tl = seeds.rover_timeline(rover)
    if not tl:
        raise HTTPException(404, "no timeline for rover")
    return {"rover": rover, "timeline": tl,
            "note": "historical imagery browsing: compare what a site looked like at different mission times",
            "provenance": prov(source="NAM panorama catalogue with sol dates and credits")}
