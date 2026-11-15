"""Mars Street View backend: panorama catalogue, camera poses, traverses,
orbital-to-ground linkage, historical imagery timelines, raw image connector."""
import json
import math
from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import config, seeds
from ..connectors import base as conn
from ..integrity import prov
from ..mars import bearing, hav_km, validate_coords

router = APIRouter(tags=["streetview"])


def _check_coords(lat: float, lon: float):
    try:
        return validate_coords(lat, lon)
    except ValueError as e:
        raise HTTPException(400, str(e))


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
    vlat, vlon = _check_coords(lat, lon)
    if not math.isfinite(radius_km) or radius_km <= 0.0:
        raise HTTPException(400, "radius_km must be a positive finite number")
    ps = seeds.panoramas_near(vlat, vlon, radius_km)
    return {"count": len(ps), "panoramas": ps,
            "provenance": prov(source="NAM panorama catalogue (NASA/JPL credits)")}


@router.get("/panoramas/raw")
def panorama_raw_feed(rover: str = "perseverance", sol: Optional[int] = None, limit: int = 12):
    """Perseverance/Mars raw-image gallery connector via NASA public RSS/JSON API.

    Fetches through the backend connector cache when upstream is enabled;
    degrades honestly with official access path & curated catalog metadata offline.
    """
    r = (rover or "perseverance").lower().strip()
    lim = max(1, min(int(limit), 30))
    cat = "mars2020" if r in ("perseverance", "mars2020") else "msl"
    official = (
        "https://mars.nasa.gov/mars2020/multimedia/raw-images/"
        if cat == "mars2020"
        else "https://mars.nasa.gov/msl/multimedia/raw-images/"
    )
    url = f"https://mars.nasa.gov/rss/api/?feed=raw_images&category={cat}&feedtype=json&num={lim}&page=0"
    if sol is not None:
        if sol < 0:
            raise HTTPException(400, "sol must be >= 0")
        url += f"&condition_2={int(sol)}:sol:gte&condition_3={int(sol)}:sol:lte"

    if not config.ALLOW_UPSTREAM:
        return {
            "rover": r,
            "status": "degraded",
            "reason": "upstream connector disabled (NAM_ALLOW_UPSTREAM=0)",
            "official_access_path": official,
            "curated_panoramas": seeds.traverse("Perseverance" if cat == "mars2020" else "Curiosity"),
            "note": "Live raw-image feed disabled in offline mode; set NAM_ALLOW_UPSTREAM=1 to fetch NASA raw frames. Curated NASA/JPL panoramas returned with credits.",
            "provenance": prov("NASA/JPL-Caltech raw-images connector (offline mode)", url=official),
        }

    try:
        body, cached = conn.fetch_bytes(url, ttl_h=1.0, retries=0)
        payload = json.loads(body.decode("utf-8", "replace"))
        raw_items = payload.get("images") or []
        items = [{
            "id": it.get("imageid"),
            "sol": it.get("sol"),
            "date_taken_utc": it.get("date_taken_utc"),
            "camera": (it.get("camera") or {}).get("instrument"),
            "title": it.get("title") or it.get("caption"),
            "credit": it.get("credit") or "NASA/JPL-Caltech",
            "thumbnail_url": (it.get("image_files") or {}).get("small") or (it.get("image_files") or {}).get("medium"),
            "full_url": (it.get("image_files") or {}).get("full_res"),
            "source_url": official,
        } for it in raw_items[:lim]]
        return {
            "rover": r, "status": "live", "cached": cached,
            "count": len(items), "images": items,
            "provenance": prov("NASA/JPL Mars Raw Images API", url=url),
        }
    except Exception as exc:
        return {
            "rover": r,
            "status": "degraded",
            "reason": str(exc),
            "official_access_path": official,
            "curated_panoramas": seeds.traverse("Perseverance" if cat == "mars2020" else "Curiosity"),
            "note": "Live NASA raw-image feed unreachable; showing curated NASA/JPL panoramas and official access path.",
            "provenance": prov("NASA/JPL-Caltech raw-images connector (degraded)", url=official),
        }


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
    vlat, vlon = _check_coords(lat, lon)
    region = seeds.rover_region(vlat, vlon)
    near = seeds.panoramas_near(vlat, vlon, radius_km=80)
    return {"lat": vlat, "lon": vlon,
            "footprint": {"deepest_layer": "CTX Murray (5 m/px)",
                          "hiRISE_inset_available": any(
                              hav_km(vlat, vlon, h["lat"], h["lon"]) < 25
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


@router.get("/sites/{rover}/compare")
def compare_historical(rover: str, a: str = None, b: str = None):
    """Compare two time-separated panoramas at the same rover site side by side."""
    pts = seeds.traverse(rover)
    if len(pts) < 2:
        raise HTTPException(404, "need at least 2 historical panoramas for rover")
    pa = next((p for p in pts if p["id"] == a), pts[0]) if a else pts[0]
    pb = next((p for p in pts if p["id"] == b), pts[-1]) if b else pts[-1]
    if a and pa["id"] != a:
        raise HTTPException(404, f"panorama {a} not found for rover {rover}")
    if b and pb["id"] != b:
        raise HTTPException(404, f"panorama {b} not found for rover {rover}")
    sol_delta = (
        (pb["sol"] - pa["sol"])
        if (pa.get("sol") is not None and pb.get("sol") is not None)
        else None
    )
    hdg_delta = ((pb["heading_deg"] - pa["heading_deg"] + 180) % 360) - 180
    return {
        "rover": pa["rover"],
        "earlier": pa,
        "later": pb,
        "delta": {
            "sol_delta": sol_delta,
            "separation_km": round(hav_km(pa["lat"], pa["lon"], pb["lat"], pb["lon"]), 3),
            "bearing_deg": round(bearing(pa["lat"], pa["lon"], pb["lat"], pb["lon"]), 1),
            "heading_delta_deg": round(hdg_delta, 1),
        },
        "provenance": prov("NASA/JPL-published historical panoramas (credits per item)"),
    }
