"""Spatial nodes of all 8 types: waypoint, hazard, water, shelter,
observation, mission, annotation, panorama_pov. Created by users or JEV."""
import math
import uuid

from . import db
from .mars import hav_km, validate_coords, validate_lat, validate_lon

NODE_TYPES = ["waypoint", "hazard", "water", "shelter", "observation", "mission", "annotation", "panorama_pov"]


def _validate_radius(radius_km):
    if radius_km is None:
        return None
    if isinstance(radius_km, bool) or not isinstance(radius_km, (int, float)):
        raise ValueError("radius_km must be numeric")
    r = float(radius_km)
    if not math.isfinite(r) or r < 0.0:
        raise ValueError("radius_km must be a non-negative finite number")
    return r


def create(ntype, lat, lon, radius_km=None, props=None, created_by="user"):
    if ntype not in NODE_TYPES:
        raise ValueError("node type must be one of " + "|".join(NODE_TYPES))
    vlat, vlon = validate_coords(lat, lon)
    vrad = _validate_radius(radius_km)
    nid = "node-" + uuid.uuid4().hex[:8]
    db.ex("INSERT INTO nodes (id,type,lat,lon,radius_km,props_json,created_by) VALUES (?,?,?,?,?,?,?)",
          (nid, ntype, vlat, vlon, vrad, db.j(props or {}), created_by))
    return get(nid)


def get(nid):
    rows = db.q("SELECT * FROM nodes WHERE id=?", (nid,))
    if not rows:
        return None
    r = rows[0]
    return {"id": r["id"], "type": r["type"], "lat": r["lat"], "lon": r["lon"],
            "radius_km": r["radius_km"], "props": db.uj(r["props_json"], {}),
            "created_by": r["created_by"], "created": r["created"]}


def list_nodes(ntype=None):
    if ntype:
        rows = db.q("SELECT * FROM nodes WHERE type=? ORDER BY created DESC", (ntype,))
    else:
        rows = db.q("SELECT * FROM nodes ORDER BY created DESC")
    return [{"id": r["id"], "type": r["type"], "lat": r["lat"], "lon": r["lon"],
             "radius_km": r["radius_km"], "props": db.uj(r["props_json"], {}),
             "created_by": r["created_by"], "created": r["created"]} for r in rows]


def update(nid, lat=None, lon=None, radius_km=None, props=None):
    vlat = validate_lat(lat) if lat is not None else None
    vlon = validate_lon(lon) if lon is not None else None
    vrad = _validate_radius(radius_km) if radius_km is not None else None
    with db.tx():
        if get(nid) is None:
            return None
        if vlat is not None:
            db.ex("UPDATE nodes SET lat=? WHERE id=?", (vlat, nid))
        if vlon is not None:
            db.ex("UPDATE nodes SET lon=? WHERE id=?", (vlon, nid))
        if vrad is not None:
            db.ex("UPDATE nodes SET radius_km=? WHERE id=?", (vrad, nid))
        if props is not None:
            db.ex("UPDATE nodes SET props_json=? WHERE id=?", (db.j(props), nid))
    return get(nid)


def delete(nid):
    """Delete a node by ID; returns True if a row was deleted, False otherwise."""
    return db.ex_count("DELETE FROM nodes WHERE id=?", (nid,)) > 0


def near(lat, lon, radius_km=100, ntype=None):
    vlat, vlon = validate_coords(lat, lon)
    vrad = _validate_radius(radius_km)
    out = []
    for n in list_nodes(ntype):
        d = hav_km(vlat, vlon, n["lat"], n["lon"])
        if d <= vrad:
            out.append(dict(n, distance_km=round(d, 1)))
    out.sort(key=lambda n: n["distance_km"])
    return out
