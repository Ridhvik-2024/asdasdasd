"""Runtime configuration (env-driven)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("NAM_DATA_DIR", ROOT / "data"))
SEEDS_DIR = DATA_DIR / "seeds"
CACHE_DIR = DATA_DIR / "cache"
TILE_CACHE_DIR = Path(os.getenv("NAM_TILE_CACHE_DIR", CACHE_DIR / "tiles"))
DB_PATH = Path(os.getenv("NAM_DB_PATH", DATA_DIR / "nam.db"))
GRID_PATH = SEEDS_DIR / "demo_grid.npz"
USGS_FULL_PATH = DATA_DIR / "usgs_gazetteer_full.json"

ALLOW_UPSTREAM = os.getenv("NAM_ALLOW_UPSTREAM", "1") == "1"
TILE_TTL_H = float(os.getenv("NAM_TILE_TTL_HOURS", "24"))
LLM_BASE_URL = os.getenv("NAM_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
LLM_MODEL = os.getenv("NAM_LLM_MODEL", "qwen2.5:1.5b") or "qwen2.5:1.5b"
CTX_TILE_TEMPLATE = os.getenv(
    "NAM_CTX_TILE_TEMPLATE",
    "https://murray-lab.caltech.edu/CTX/V01/TileData/Z{z}/{y}_{x}.jpg")

# Optional security / deployment settings.
# When NAM_API_KEY is empty (default for reference-laptop & automated gates),
# local unauthenticated requests are permitted. When set, mutating endpoints
# require X-API-Key or Authorization: Bearer <key>.
API_KEY = os.getenv("NAM_API_KEY", "").strip()
CORS_ORIGINS = [
    o.strip() for o in os.getenv("NAM_CORS_ORIGINS", "*").split(",") if o.strip()
] or ["*"]

VERSION = "2.3.0"
RELEASES = [
    {"phase": 1, "release": "v2.0.0-backend", "title": "The Google Earth Core",
     "scope": "terrain engine, imagery ladder + tile proxy, gazetteer + search + location cards, measurement suite, integrity layer"},
    {"phase": 2, "release": "v2.1.0-backend", "title": "Mars Street View and the Scientific Explorer",
     "scope": "science layer registry, discoveries, landing-site compare, panoramas/traverses/linkage, Walk View"},
    {"phase": 3, "release": "v2.2.0-backend-ai", "title": "JEV intelligent explorer",
     "scope": "24 typed tools, intent router, OpenAI-compatible LLM adapter, retrieval, SSE chat, explain-view, benchmark"},
    {"phase": 4, "release": "v2.2.1-backend-missions", "title": "Missions and environment",
     "scope": "A* routing engine, mission suite (4 types, KML, optimize), radiation/SEP/dust sims, water and shelter discovery"},
    {"phase": 5, "release": "v2.2.2-backend-live", "title": "Real-time and closing",
     "scope": "nodes (8 types), presence, WebSocket channels with bounded rates, storm drill, self-test"},
]

for d in (DATA_DIR, SEEDS_DIR, TILE_CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
