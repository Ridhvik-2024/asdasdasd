"""Mars geodesy and solar geometry (IAU ellipsoid, east 0-360 longitude).

Solar timing follows the NASA GISS Mars24 algorithm:
  Allison, M., & McEwen, M. (2000), "A post-Pathfinder evaluation of
  areocentric solar coordinates with improved timing recipes for Mars
  seasonal/diurnal climate studies", Planetary and Space Science, 48, 215-235.
"""
import math
from datetime import datetime, timezone

A_EQ = 3396.19       # km, IAU Mars equatorial radius
B_POL = 3376.20      # km, IAU Mars polar radius
MEAN_R = 3389.5      # km
KM_PER_DEG = 59.3    # approximate surface km per degree of latitude
OBLIQUITY = 25.1919  # deg, Mars axial obliquity (Allison & McEwen 2000)
SOL_SEC = 88775.244  # Mars solar day (24h 39m 35.244s)


def validate_lat(lat):
    """Validate Mars latitude in [-90, 90] instead of silently clamping."""
    if isinstance(lat, bool) or not isinstance(lat, (int, float)):
        raise ValueError("latitude must be a finite number")
    val = float(lat)
    if not math.isfinite(val) or val < -90.0 or val > 90.0:
        raise ValueError("latitude must be between -90 and 90 degrees (got %r)" % lat)
    return val


def validate_lon(lon):
    """Validate finite longitude and normalize to east [0, 360)."""
    if isinstance(lon, bool) or not isinstance(lon, (int, float)):
        raise ValueError("longitude must be a finite number")
    val = float(lon)
    if not math.isfinite(val):
        raise ValueError("longitude must be finite (got %r)" % lon)
    return val % 360.0


def validate_coords(lat, lon):
    """Validate (lat, lon) and return (lat_deg, norm_lon_deg)."""
    return validate_lat(lat), validate_lon(lon)


def norm_lon(lon):
    """Normalize any finite longitude input to east 0-360."""
    val = float(lon)
    if not math.isfinite(val):
        raise ValueError("longitude must be finite")
    return val % 360.0


def norm_lat(lat):
    """Clamp slight numerical overshoot (e.g. geodesic forward steps); reject NaN/Inf."""
    val = float(lat)
    if not math.isfinite(val):
        raise ValueError("latitude must be finite")
    return max(-90.0, min(90.0, val))


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
    p2 = math.asin(max(-1.0, min(1.0, math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(az))))
    l2 = l1 + math.atan2(math.sin(az) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return norm_lat(math.degrees(p2)), norm_lon(math.degrees(l2))


def poly_area_km2(points):
    """Spherical polygon area (km2) using exact spherical geodesic edge excess.

    Handles:
      * Antimeridian-crossing polygons (e.g. 359 deg -> 1 deg uses 2 deg step,
        not 358 deg).
      * Large regional/continental polygons via exact spherical trapezoid
        excess 2 * atan2(tan(dlam/2) * sin((phi_i + phi_j)/2), cos((phi_i - phi_j)/2)).
      * Polar-enclosing polygons whose closed longitude loop winds +/-360 deg
        around the North or South Pole.
    """
    if len(points) < 3:
        return 0.0
    lats = [validate_lat(p["lat"] if isinstance(p, dict) else p[0]) for p in points]
    raw = [validate_lon(p["lon"] if isinstance(p, dict) else p[1]) for p in points]
    n = len(points)
    phis = [math.radians(x) for x in lats]
    dlams = [((raw[(i + 1) % n] - raw[i] + 180.0) % 360.0) - 180.0 for i in range(n)]
    winding = round(sum(dlams) / 360.0)

    total_sr = 0.0
    for i in range(n):
        j = (i + 1) % n
        dl = math.radians(dlams[i])
        total_sr += 2.0 * math.atan2(
            math.tan(dl / 2.0) * math.sin((phis[i] + phis[j]) / 2.0),
            math.cos((phis[i] - phis[j]) / 2.0),
        )
    if winding != 0:
        solid_angle = abs(2.0 * math.pi * abs(winding) - abs(total_sr))
        r = B_POL if abs(sum(lats) / n) > 75.0 else local_radius_km(sum(lats) / n)
    else:
        solid_angle = abs(total_sr)
        r = local_radius_km(sum(lats) / n)
    return solid_angle * r * r


def _tt_minus_utc_seconds(year):
    """Piecewise TT - UTC offset (seconds) sufficient for sub-second Mars solar geometry."""
    if year < 1999:
        return 63.184
    if year < 2006:
        return 64.184
    if year < 2009:
        return 65.184
    if year < 2012:
        return 66.184
    if year < 2015:
        return 67.184
    if year < 2017:
        return 68.184
    return 69.184


def subsolar(dt_utc, ls_deg=None):
    """Mars subsolar point and seasonal state via Allison & McEwen (2000) / Mars24.

    Computes Julian Date (TT), Mars Sol Date (MSD), Coordinated Mars Time (MTC),
    Mars Mean Anomaly M, Equation of Center (v - M), Areocentric Solar Longitude
    Ls (computed from orbital epoch when ls_deg is None, or overridden if
    supplied), Equation of Time (EOT), solar declination, and subsolar east
    longitude in [0, 360).
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt_utc.astimezone(timezone.utc)

    jd_utc = 2440587.5 + dt_utc.timestamp() / 86400.0
    jd_tt = jd_utc + _tt_minus_utc_seconds(dt_utc.year) / 86400.0
    dt_j2000 = jd_tt - 2451545.0

    mean_anom = (19.3871 + 0.52402073 * dt_j2000) % 360.0
    alpha_fms = (270.3871 + 0.524038496 * dt_j2000) % 360.0
    mr = math.radians(mean_anom)
    v_minus_m = (
        (10.691 + 3.0e-7 * dt_j2000) * math.sin(mr)
        + 0.623 * math.sin(2.0 * mr)
        + 0.050 * math.sin(3.0 * mr)
        + 0.005 * math.sin(4.0 * mr)
        + 0.0005 * math.sin(5.0 * mr)
    )
    computed_ls = (alpha_fms + v_minus_m) % 360.0
    ls_used = float(ls_deg) % 360.0 if ls_deg is not None else computed_ls
    ls_rad = math.radians(ls_used)

    eot_deg = (
        2.861 * math.sin(2.0 * ls_rad)
        - 0.071 * math.sin(4.0 * ls_rad)
        + 0.002 * math.sin(6.0 * ls_rad)
        - v_minus_m
    )
    msd = (jd_tt - 2451549.5) / 1.0274912517 + 44796.0 - 0.0009626
    mtc_hours = (msd % 1.0) * 24.0
    subsolar_lon_west = (mtc_hours * 15.0 + eot_deg + 180.0) % 360.0
    lon_sub_east = (360.0 - subsolar_lon_west) % 360.0

    sin_dec = math.sin(math.radians(OBLIQUITY)) * math.sin(ls_rad)
    dec = math.degrees(math.asin(max(-1.0, min(1.0, sin_dec))))

    method = (
        "Allison & McEwen (2000) Mars24 orbital/rotational model (explicit Ls override)"
        if ls_deg is not None
        else "Allison & McEwen (2000) Mars24 orbital/rotational model"
    )
    return {
        "lat": round(dec, 6),
        "lon": round(lon_sub_east, 6),
        "ls_deg": round(ls_used, 4),
        "msd": round(msd, 5),
        "mtc_hours": round(mtc_hours, 5),
        "method": method,
        "sim": True,
    }


def sun_geometry(lat, lon, iso_time, ls_deg=None, slope_deg=None, azimuth_deg=None):
    """Solar elevation, azimuth and incidence angle at a Mars surface point [SIM]."""
    lat, lon = validate_coords(lat, lon)
    dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    sub = subsolar(dt, ls_deg)
    phi = math.radians(lat)
    dec = math.radians(sub["lat"])
    H = math.radians(((lon - sub["lon"] + 180.0) % 360.0) - 180.0)
    sin_e = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(H)
    sin_e = max(-1.0, min(1.0, sin_e))
    elev = math.degrees(math.asin(sin_e))
    cos_e = math.cos(math.asin(sin_e))
    denom = math.cos(phi) * cos_e
    if abs(denom) < 1e-9:
        az = 180.0 if lat >= 0.0 else 0.0
    else:
        cos_az = (math.sin(dec) - math.sin(phi) * sin_e) / denom
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        if math.sin(H) > 0.0:
            az = 360.0 - az
    ltst_hours = (12.0 + (((lon - sub["lon"] + 180.0) % 360.0) - 180.0) / 15.0) % 24.0
    out = {
        "subsolar": sub,
        "sun_elevation_deg": elev,
        "sun_azimuth_deg": az % 360.0,
        "local_true_solar_time_h": round(ltst_hours, 4),
        "provenance": {
            "source": "NAM solar geometry (Allison & McEwen 2000 / NASA Mars24) [SIM]",
            "method": sub["method"],
        },
    }
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
