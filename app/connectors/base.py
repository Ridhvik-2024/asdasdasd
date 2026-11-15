"""External-source connectors: discover, fetch, persistent cache, attribute, degrade."""
import hashlib
import json
import time
from pathlib import Path

import httpx

from .. import config
from ..integrity import prov

REGISTRY = [
    {"name": "ctx-murray", "purpose": "Caltech Murray Lab Global CTX Mosaic tiles (~5 m/px, default surface layer)",
     "url": "https://murray-lab.caltech.edu/CTX/", "template": config.CTX_TILE_TEMPLATE,
     "status": "unverified", "attribution": "Caltech/MSSS/NASA JPL - Bruce Murray Lab"},
    {"name": "usgs-wms", "purpose": "USGS Astrogeology WMS/WTS (MOLA, THEMIS, SIM 3292 geology tiles)",
     "url": "https://wms.wr.usgs.gov/", "template": "https://wms.wr.usgs.gov/wms.cgi?VERSION=1.3.0&SERVICE=WMS&REQUEST=GetMap&LAYERS={layer}&CRS=CRS:84&BBOX={bbox}&WIDTH={w}&HEIGHT={h}&FORMAT=image/png",
     "status": "unverified", "attribution": "USGS Astrogeology Science Center"},
    {"name": "opm", "purpose": "OpenPlanetaryMap Mars basemaps/tiles",
     "url": "https://openplanetary.org/", "template": None, "status": "unverified",
     "attribution": "OpenPlanetary Foundation"},
    {"name": "pds-imaging", "purpose": "NASA PDS Imaging Node datasets (Viking MDIM 2.1, CRISM, rover archives)",
     "url": "https://pds-imaging.jpl.nasa.gov/", "template": None, "status": "unverified",
     "attribution": "NASA PDS"},
    {"name": "mars-raw", "purpose": "Perseverance/Curiosity raw image galleries (JSON/RSS feed investigated at connector time)",
     "url": "https://mars.nasa.gov/raw_images/", "template": None, "status": "unverified",
     "attribution": "NASA/JPL-Caltech"},
    {"name": "swim", "purpose": "SWIM subsurface water-ice mapping project",
     "url": "https://swim.psi.edu", "template": None, "status": "unverified",
     "attribution": "NASA/JPL/PSI SWIM team"},
    {"name": "gazetteer", "purpose": "USGS Gazetteer of Planetary Nomenclature (full Mars nomenclature KMZ)",
     "url": "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MARS_nomenclature_center_pts.kmz",
     "template": None, "status": "verified",
     "attribution": "USGS Astrogeology / IAU"},
    {"name": "mars-trek", "purpose": "NASA Mars Trek (reference implementation and measurement parity source)",
     "url": "https://marstrek.nasa.gov", "template": None, "status": "unverified",
     "attribution": "NASA/JPL-Caltech"},
]

_cache: dict = {}
_stats = {"hits": 0, "disk_hits": 0, "misses": 0, "errors": 0}


def _cache_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]


def _disk_paths(key: str):
    cache_dir = Path(config.TILE_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.bin", cache_dir / f"{key}.meta.json"


def _read_disk_cache(key: str, ttl_s: float):
    bin_path, meta_path = _disk_paths(key)
    if not bin_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ts = float(meta.get("ts", 0.0))
        if time.time() - ts >= ttl_s:
            return None
        data = bin_path.read_bytes()
        return ts, data
    except Exception:
        return None


def _write_disk_cache(key: str, url: str, ts: float, data: bytes):
    try:
        bin_path, meta_path = _disk_paths(key)
        bin_path.write_bytes(data)
        meta_path.write_text(json.dumps({"url": url, "ts": ts, "size": len(data)}), encoding="utf-8")
    except Exception:
        pass


def invalidate_cache(url: str = None):
    """Invalidate one cached URL or clear the entire memory + persistent disk cache."""
    if url is not None:
        key = _cache_key(url)
        _cache.pop(key, None)
        bin_path, meta_path = _disk_paths(key)
        for p in (bin_path, meta_path):
            p.unlink(missing_ok=True)
        return
    _cache.clear()
    cache_dir = Path(config.TILE_CACHE_DIR)
    if cache_dir.exists():
        for p in cache_dir.glob("*"):
            if p.is_file() and (p.suffix == ".bin" or p.name.endswith(".meta.json")):
                p.unlink(missing_ok=True)


def detect_image_media_type(data: bytes):
    """Detect image MIME type from magic bytes; returns None if not a valid image."""
    if not data or len(data) < 8:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return None


def status():
    return {"connectors": REGISTRY, "stats": _stats,
            "cache_dir": str(config.TILE_CACHE_DIR),
            "upstream_allowed": config.ALLOW_UPSTREAM}


def get(name):
    for c in REGISTRY:
        if c["name"] == name:
            return c
    return None


def verify(name):
    c = get(name)
    if not c:
        return None
    if not config.ALLOW_UPSTREAM:
        c["status"] = "offline-allowed=false"
        return c
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as cl:
            r = cl.head(c["url"])
        c["status"] = "verified" if r.status_code < 500 else "degraded (%s)" % r.status_code
    except Exception as e:
        c["status"] = "degraded (%s)" % type(e).__name__
    return c


def fetch_bytes(url, ttl_h=None, retries=1):
    """Fetch with in-memory + persistent disk cache and retry; returns (bytes, cached_flag)."""
    key = _cache_key(url)
    now = time.time()
    ttl = (ttl_h if ttl_h is not None else config.TILE_TTL_H) * 3600.0

    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        _stats["hits"] += 1
        return hit[1], True

    disk_hit = _read_disk_cache(key, ttl)
    if disk_hit is not None:
        _cache[key] = disk_hit
        _stats["hits"] += 1
        _stats["disk_hits"] += 1
        return disk_hit[1], True

    _stats["misses"] += 1
    last_exc = None
    for attempt in range(max(1, int(retries) + 1)):
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as cl:
                r = cl.get(url)
                r.raise_for_status()
                data = r.content
            break
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                raise
    else:
        raise last_exc

    ts = time.time()
    _cache[key] = (ts, data)
    _write_disk_cache(key, url, ts, data)
    if len(_cache) > 4000:
        for k in list(_cache)[:800]:
            _cache.pop(k, None)
    return data, False


def provenance_for(name):
    c = get(name)
    if not c:
        return prov(source="unknown connector")
    return prov(source=c["name"], url=c["url"], note=c["attribution"])
