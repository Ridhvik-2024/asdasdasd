"""SQLite persistence layer (reference-laptop default).

The production PostGIS path is provided in infra/postgis_schema.sql and
docker-compose.yml; this DAO keeps a single-file DB so the whole platform runs
on one developer machine as the build plan requires.
"""
from contextlib import contextmanager
import json
import sqlite3
import threading

from . import config

_lock = threading.RLock()
_conn = None
_tx_depth = 0

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookmarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  lat REAL NOT NULL, lon REAL NOT NULL,
  camera_json TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS share_links (
  id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  lat REAL NOT NULL, lon REAL NOT NULL,
  radius_km REAL,
  props_json TEXT,
  created_by TEXT DEFAULT 'user',
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS missions (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  objective TEXT,
  status TEXT DEFAULT 'draft',
  notes TEXT,
  advisory INTEGER DEFAULT 1,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mission_stops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mission_id TEXT NOT NULL,
  ord INTEGER NOT NULL,
  lat REAL, lon REAL,
  activity TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS routes (
  id TEXT PRIMARY KEY,
  mission_id TEXT,
  preset TEXT,
  length_km REAL,
  stats_json TEXT,
  path_json TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chat_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT CURRENT_TIMESTAMP,
  role TEXT, content TEXT
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_mission_stops_mission_ord ON mission_stops(mission_id, ord);
CREATE INDEX IF NOT EXISTS idx_routes_mission ON routes(mission_id, created DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type, created DESC);
"""

MIGRATIONS = [
    (1, "initial_core_tables_and_indexes", ""),
]


def init_db():
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:
            return _conn
        conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        applied = {
            r["version"]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for ver, name, ddl in MIGRATIONS:
            if ver not in applied:
                if ddl:
                    conn.executescript(ddl)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (ver, name),
                )
        _conn = conn
    return _conn


@contextmanager
def tx():
    """Thread-safe, re-entrant atomic SQLite transaction context manager."""
    global _tx_depth
    c = init_db()
    with _lock:
        outermost = _tx_depth == 0
        if outermost:
            c.execute("BEGIN IMMEDIATE")
        _tx_depth += 1
        try:
            yield c
        except Exception:
            _tx_depth -= 1
            if outermost:
                c.execute("ROLLBACK")
            raise
        else:
            _tx_depth -= 1
            if outermost:
                c.execute("COMMIT")


def q(sql, params=()):
    c = init_db()
    with _lock:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def ex(sql, params=()):
    c = init_db()
    with _lock:
        cur = c.execute(sql, params)
    return cur.lastrowid


def ex_count(sql, params=()):
    """Execute a statement and return the number of affected rows."""
    c = init_db()
    with _lock:
        cur = c.execute(sql, params)
    return cur.rowcount


def j(obj):
    return json.dumps(obj, ensure_ascii=False)


def uj(text, default=None):
    try:
        return json.loads(text)
    except Exception:
        return default
