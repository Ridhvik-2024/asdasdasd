"""NAM integrity rules (non-negotiable, enforced at the service layer).

- Every scientific value carries provenance (source, mission, instrument,
  resolution, date, url).
- Unavailable services degrade to documented status with access paths,
  never faked.
- All simulations and estimates carry the [SIM] label and are advisory.
- Coordinates: latitude degrees (south negative), longitude EAST 0-360.
"""
SIM = "[SIM]"


def prov(source, mission=None, instrument=None, resolution=None, date=None, url=None, note=None):
    """Build a provenance block. All fields except source are optional."""
    return {
        "source": source,
        "mission": mission,
        "instrument": instrument,
        "resolution": resolution,
        "date": date,
        "url": url,
        "note": note,
    }


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
