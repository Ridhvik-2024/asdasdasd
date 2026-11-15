"""Spatial nodes CRUD (8 types) and presence endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import nodes, presence

router = APIRouter(tags=["nodes_and_presence"])


class NodeIn(BaseModel):
    type: str
    lat: float
    lon: float
    radius_km: float = None
    props: dict = {}
    created_by: str = "user"


@router.post("/nodes")
def create_node(n: NodeIn):
    try:
        return nodes.create(n.type, n.lat, n.lon, n.radius_km, n.props, n.created_by)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/nodes")
def list_nodes(type: str = None):
    items = nodes.list_nodes(type)
    return {"count": len(items), "nodes": items,
            "note": "8 node types: waypoint|hazard|water|shelter|observation|mission|annotation|panorama_pov"}


@router.get("/nodes/near")
def nodes_near(lat: float, lon: float, radius_km: float = 100, type: str = None):
    try:
        items = nodes.near(lat, lon, radius_km, type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"count": len(items), "nodes": items}


@router.get("/nodes/{nid}")
def get_node(nid: str):
    n = nodes.get(nid)
    if not n:
        raise HTTPException(404, "unknown node")
    return n


class NodeUpd(BaseModel):
    lat: float = None
    lon: float = None
    radius_km: float = None
    props: dict = None


@router.put("/nodes/{nid}")
def update_node(nid: str, u: NodeUpd):
    try:
        n = nodes.update(nid, u.lat, u.lon, u.radius_km, u.props)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not n:
        raise HTTPException(404, "unknown node")
    return n


@router.delete("/nodes/{nid}")
def delete_node(nid: str):
    if not nodes.delete(nid):
        raise HTTPException(404, "unknown node")
    return {"deleted": True}


# ------------------------------------------------------------------ presence
@router.get("/presence/agents")
def presence_agents():
    return {"agents": presence.agents(),
            "provenance": {"source": "NAM presence simulation [SIM]"}}


@router.get("/presence/agents/{aid}")
def presence_agent(aid: str):
    a = presence.agent(aid)
    if not a:
        raise HTTPException(404, "unknown agent")
    return a


@router.get("/presence/near")
def presence_near(lat: float, lon: float, radius_km: float = 200):
    try:
        items = presence.near(lat, lon, radius_km)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"agents": items}


@router.post("/presence/tick")
def presence_tick(dt_sols: float = 1.0):
    try:
        items = presence.tick(dt_sols)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"agents": items,
            "note": "advances the [SIM] presence simulation"}


@router.get("/presence/types")
def presence_types():
    return {"kinds": ["crew", "rover", "habitat"],
            "lookup": "GET /presence/near?lat&lon&radius_km"}
