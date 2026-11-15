"""Mars geodesy and solar geometry (IAU ellipsoid, east 0-360 longitude)."""
import math
from datetime import datetime, timezone

A_EQ = 3396.19      # km, IAU Mars equatorial radius
B_POL = 3376.20     # km, IAU Mars polar radius
MEAN_R = 3389.5     # km
KM_PER_DEG = 59.3   # approximate surface km per degree of latitude
OBLIQUITY = 25.19   # deg
SOL_SEC = 88775.244 # Mars solar day (24h 39m 35.244s)


def norm_lon(lon):
    """Normalize any longitude input to east 0-360."""
    lon = float(lon) % 360.0
    return lon


def norm_lat(lat):
    lat = max(-90.0, min(90.0, float(lat)))
    return lat


def local_radius_km(lat):
    """Ellipsoid surface radius at geodetic latitude."""
    phi = math.radians(lat)
    e2 = 1.0 - (B_POL / A_EQ) ** 2
    return A_EQ / math.sqrt(1.0 - e2 * math.sin(phi) ** 2)


def hav_km(lat1, lon1, lat2, lon2):
    """Great-circle distance on the local ellipsoid radius (documented
    approximation, ~0.1 percent class error vs full geodesics)."""
    lat1, lat2 = norm_lat(lat1), norm_lat(lat2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(((lon2 - lon1 + 180) % 360) - 180)
    dp = p2 - p1
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    r = local_radius_km((lat1 + lat2) / 2.0)
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(((lon2 - lon1 + 180) % 360) - 180)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def dest_pt(lat, lon, dist_km, az_deg):
    """Destination point given distance and initial bearing."""
    r = local_radius_km(lat)
    d = dist_km / r
    az = math.radians(az_deg)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(az))
    l2 = l1 + math.atan2(math.sin(az) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return norm_lat(math.degrees(p2)), norm_lon(math.degrees(l2))


def poly_area_km2(points):
    """Spherical polygon area (km2) via the shoelace formula on a sphere."""
    if len(points) < 3:
        return 0.0
    lats = [norm_lat(p["lat"] if isinstance(p, dict) else p[0]) for p in points]
    lons = [norm_lon(p["lon"] if isinstance(p, dict) else p[1]) for p in points]
    phi = [math.radians(x) for x in lats]
    lam = [math.radians(x) for x in lons]
    total = 0.0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        total += (lam[j] - lam[i]) * (math.sin(phi[i]) + math.sin(phi[j])) / 2.0
    r = local_radius_km(sum(lats) / len(lats))
    return abs(total) * r * r


def subsolar(dt_utc, ls_deg=None):
    """Approximate subsolar point for a UTC time.

    Without an areocentric longitude Ls the seasonal term is skipped
    (equinox approximation) and the result is labelled approximate [SIM].
    With ls_deg provided the seasonal declination is included [SIM].
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    frac = (dt_utc.timestamp() % SOL_SEC) / SOL_SEC
    lon_sub = norm_lon(180.0 - 360.0 * frac)
    if ls_deg is None:
        return {"lat": 0.0, "lon": lon_sub, "method": "circular-orbit equinox approximation",
                "sim": True,
                "note": "pass ls_deg (areocentric solar longitude) for seasonal accuracy"}
    dec = OBLIQUITY * math.sin(math.radians(ls_deg))
    return {"lat": dec, "lon": lon_sub, "method": "circular-orbit with Ls seasonal term",
            "sim": True, "ls_deg": ls_deg}


def sun_geometry(lat, lon, iso_time, ls_deg=None, slope_deg=None, azimuth_deg=None):
    """Solar elevation, azimuth and incidence angle at a point [SIM]."""
    dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    sub = subsolar(dt, ls_deg)
    phi = math.radians(lat)
    dec = math.radians(sub["lat"])
    H = math.radians(((lon - sub["lon"] + 180) % 360) - 180)
    sin_e = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(H)
    sin_e = max(-1.0, min(1.0, sin_e))
    elev = math.degrees(math.asin(sin_e))
    cos_az = (math.sin(dec) - math.sin(phi) * sin_e) / max(1e-9, math.cos(phi) * math.cos(math.asin(sin_e)))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if H > 0:
        az = 360.0 - az
    out = {"subsolar": sub, "sun_elevation_deg": elev, "sun_azimuth_deg": az,
           "provenance": {"source": "NAM solar geometry model [SIM] (approximate orbital mechanics)",
                          "method": sub["method"]}}
    if slope_deg is None:
        out["incidence_deg"] = 90.0 - elev
        out["incidence_note"] = "flat surface"
    else:
        zen = math.radians(90.0 - elev)
        sl = math.radians(slope_deg)
        da = math.radians(az - (azimuth_deg or 0.0))
        ci = math.cos(zen) * math.cos(sl) + math.sin(zen) * math.sin(sl) * math.cos(da)
        out["incidence_deg"] = math.degrees(math.acos(max(-1.0, min(1.0, ci))))
        out["incidence_note"] = "on slope of %.1f deg facing azimuth %.1f" % (slope_deg, azimuth_deg or 0.0)
    return out
