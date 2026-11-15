"""Water-ice and shelter discovery with scoring logic [SIM] on SWIM data."""
from . import seeds
from .mars import hav_km, norm_lat, norm_lon
from .integrity import with_sim

CERTAINTY_ORDER = {"A": 3, "B": 2, "C": 1}


def find_water(bbox=None, near=None, radius_km=600, min_certainty=None):
    out = []
    for w in seeds.water_all():
        if min_certainty and CERTAINTY_ORDER.get(w["certainty"], 0) < CERTAINTY_ORDER.get(min_certainty.upper(), 3):
            continue
        w = dict(w)
        w["depth_to_ice_category"] = _depth_cat(w["depth_to_ice_m"])
        w["stability"] = _stability(w)
        if bbox and not _in_bbox(w["lat"], w["lon"], bbox):
            continue
        if near:
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
    out = []
    for s in seeds.shelters_all():
        s = dict(score_shelter(s))
        if bbox and not _in_bbox(s["lat"], s["lon"], bbox):
            continue
        if near:
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
    comp = 0.4 * s["shielding"] + 0.25 * s["thermal"] + 0.2 * s["access"]
    # proximity band: candidates at mid latitudes near landing regions are
    # operationally easier; small bonus, capped contribution
    comp += 0.15 * max(0.0, 100 - abs(s["lat"]) / 2)
    s["composite_index"] = round(min(100.0, comp), 1)
    s["provenance"] = {
        "source": "NAM curated candidate set with deterministic scoring [SIM]",
        "note": "coordinates approximate - verify against HiRISE before any use",
    }
    return s
