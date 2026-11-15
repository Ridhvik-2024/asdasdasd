"""NAM integrity rules (non-negotiable, enforced at the service layer).

- Every scientific value carries provenance (source, mission, instrument,
  resolution, date, url).
- Unavailable services degrade to documented status with access paths,
  never faked.
- All simulations and estimates carry the [SIM] label and are advisory.
- Coordinates: latitude degrees (south negative), longitude EAST 0-360.
"""
SIM = "[SIM]"
QUALITY_TIERS = ("observed", "derived", "simulated", "predicted")


def prov(source, mission=None, instrument=None, resolution=None, date=None,
         url=None, note=None, quality=None, attribution=None):
    """Build a provenance block with standardized data-quality tier metadata."""
    if quality not in QUALITY_TIERS:
        src_low = (source or "").lower()
        if "[sim]" in src_low or "synthetic" in src_low or "simulated" in src_low:
            quality = "simulated"
        elif "derived" in src_low or "scaling" in src_low or "comparison" in src_low:
            quality = "derived"
        else:
            quality = "observed"
    out = {
        "source": source,
        "quality": quality,
        "mission": mission,
        "instrument": instrument,
        "resolution": resolution,
        "date": date,
        "url": url,
        "note": note,
    }
    if attribution is not None:
        out["attribution"] = attribution
    return out


def with_sim(payload, note=None):
    """Attach the [SIM] advisory label to a payload."""
    payload["sim"] = True
    payload["advisory"] = "Simulation/estimate - advisory only. " + (note or "")
    payload["provenance"] = {"source": "NAM deterministic model " + SIM, "note": note}
    return payload


def degraded(service, reason, access_path):
    """Honest degradation: document what is unavailable and how to reach it."""
    return {
        "status": "degraded",
        "service": service,
        "reason": reason,
        "access_path": access_path,
        "sim": False,
    }


def wrap(payload, provenance):
    payload["provenance"] = provenance
    return payload
