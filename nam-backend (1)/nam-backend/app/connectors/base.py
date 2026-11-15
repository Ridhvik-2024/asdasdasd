"""External-source connectors: discover, fetch, cache, attribute, degrade."""
import hashlib
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
_stats = {"hits": 0, "misses": 0, "errors": 0}


def status():
    return {"connectors": REGISTRY, "stats": _stats,
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


def fetch_bytes(url, ttl_h=None):
    """Fetch with a process cache; returns (bytes, cached_flag)."""
    key = hashlib.sha1(url.encode()).hexdigest()[:24]
    now = time.time()
    ttl = (ttl_h if ttl_h is not None else config.TILE_TTL_H) * 3600.0
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        _stats["hits"] += 1
        return hit[1], True
    _stats["misses"] += 1
    with httpx.Client(timeout=10.0, follow_redirects=True) as cl:
        r = cl.get(url)
        r.raise_for_status()
        data = r.content
    _cache[key] = (now, data)
    if len(_cache) > 4000:
        for k in list(_cache)[:800]:
            _cache.pop(k, None)
    return data, False


def provenance_for(name):
    c = get(name)
    if not c:
        return prov(source="unknown connector")
    return prov(source=c["name"], url=c["url"], note=c["attribution"])
