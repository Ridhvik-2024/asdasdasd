"""Water-ice and shelter discovery with scoring logic [SIM] on SWIM data."""
import math

from . import seeds
from .mars import hav_km, validate_coords, validate_lat, validate_lon
from .integrity import with_sim

CERTAINTY_ORDER = {"A": 3, "B": 2, "C": 1}


def _validate_radius(radius_km):
    if isinstance(radius_km, bool) or not isinstance(radius_km, (int, float)):
        raise ValueError("radius_km must be a finite number")
    val = float(radius_km)
    if not math.isfinite(val) or val <= 0.0:
        raise ValueError("radius_km must be > 0 (got %r)" % radius_km)
    return val


def _validate_bbox(bbox):
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("bbox must have 4 elements [min_lat, min_lon, max_lat, max_lon]")
    min_lat = validate_lat(bbox[0])
    min_lon = validate_lon(bbox[1])
    max_lat = validate_lat(bbox[2])
    max_lon = validate_lon(bbox[3])
    return min_lat, float(bbox[1]), max_lat, float(bbox[3]), min_lon, max_lon


def _in_bbox(lat, lon, bbox):
    """Antimeridian-aware bounding-box containment check (lon east 0-360)."""
    lat_v, lon_v = validate_coords(lat, lon)
    min_lat, raw_min_lon, max_lat, raw_max_lon, min_lon, max_lon = _validate_bbox(bbox)
    lat_lo, lat_hi = (min_lat, max_lat) if min_lat <= max_lat else (max_lat, min_lat)
    if not (lat_lo <= lat_v <= lat_hi):
        return False
    if (raw_max_lon - raw_min_lon) >= 360.0:
        return True
    if min_lon <= max_lon:
        return min_lon <= lon_v <= max_lon
    # Antimeridian-crossing bbox: [min_lon, 360) U [0, max_lon]
    return lon_v >= min_lon or lon_v <= max_lon


def find_water(bbox=None, near=None, radius_km=600, min_certainty=None):
    if bbox is not None:
        _validate_bbox(bbox)
    if near is not None:
        nlat, nlon = validate_coords(near["lat"], near["lon"])
        near = {"lat": nlat, "lon": nlon}
        radius_km = _validate_radius(radius_km)
    out = []
    for w in seeds.water_all():
        if min_certainty and CERTAINTY_ORDER.get(w["certainty"], 0) < CERTAINTY_ORDER.get(min_certainty.upper(), 3):
            continue
        w = dict(w)
        w["depth_to_ice_category"] = _depth_cat(w["depth_to_ice_m"])
        w["stability"] = _stability(w)
        if bbox is not None and not _in_bbox(w["lat"], w["lon"], bbox):
            continue
        if near is not None:
            d = hav_km(near["lat"], near["lon"], w["lat"], w["lon"])
            if d > radius_km:
                continue
            w["distance_km"] = round(d, 1)
        out.append(w)
    out.sort(key=lambda w: -CERTAINTY_ORDER.get(w["certainty"], 0))
    return out


def _depth_cat(dr):
    lo, hi = dr
    if lo < 1.0:
        return "exposed/very shallow (<1 m locally)"
    if lo <= 5.0:
        return "shallow (1-5 m)"
    return "deep (>5 m)"


def _stability(w):
    """Latitude/elevation stability logic [SIM]: mid/high-latitude ground ice
    is stable over geologic time; equatorial ice is not."""
    lat = abs(w["lat"])
    if lat >= 45:
        return "stable [SIM]: latitude >= 45 deg supports long-term shallow ice"
    if lat >= 30:
        return "conditionally stable [SIM]: latitude band 30-45 deg, burial needed"
    return "unstable at surface [SIM]: equatorial band, ice survives only buried/insulated"


def find_shelter(bbox=None, near=None, radius_km=600):
    if bbox is not None:
        _validate_bbox(bbox)
    if near is not None:
        nlat, nlon = validate_coords(near["lat"], near["lon"])
        near = {"lat": nlat, "lon": nlon}
        radius_km = _validate_radius(radius_km)
    out = []
    for s in seeds.shelters_all():
        s = dict(score_shelter(s))
        if bbox is not None and not _in_bbox(s["lat"], s["lon"], bbox):
            continue
        if near is not None:
            d = hav_km(near["lat"], near["lon"], s["lat"], s["lon"])
            if d > radius_km:
                continue
            s["distance_km"] = round(d, 1)
        out.append(s)
    out.sort(key=lambda s: -s["composite_index"])
    return out


def score_shelter(s):
    """Composite shelter index [SIM]: 0.4 shielding + 0.25 thermal +
    0.2 access + 0.15 proximity-band score."""
    s = dict(s)
    vlat, vlon = validate_coords(s["lat"], s["lon"])
    s["lat"], s["lon"] = vlat, vlon
    for key in ("shielding", "thermal", "access"):
        val = s[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(float(val)):
            raise ValueError("%s must be a finite number" % key)
    comp = 0.4 * s["shielding"] + 0.25 * s["thermal"] + 0.2 * s["access"]
    # proximity band: candidates at mid latitudes near landing regions are
    # operationally easier; small bonus, capped contribution
    comp += 0.15 * max(0.0, 100 - abs(vlat) / 2)
    s["composite_index"] = round(min(100.0, comp), 1)
    s["provenance"] = {
        "source": "NAM curated candidate set with deterministic scoring [SIM]",
        "note": "coordinates approximate - verify against HiRISE before any use",
    }
    return s
