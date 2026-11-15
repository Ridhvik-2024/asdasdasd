"""SQLite persistence layer (reference-laptop default).

The production PostGIS path is provided in infra/postgis_schema.sql and
docker-compose.yml; this DAO keeps a single-file DB so the whole platform runs
on one developer machine as the build plan requires.
"""
import json
import sqlite3
import threading

from . import config

_lock = threading.Lock()
_conn = None

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
"""


def init_db():
    global _conn
    if _conn is not None:
        return _conn
    _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    with _lock:
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def q(sql, params=()):
    c = init_db()
    with _lock:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def ex(sql, params=()):
    c = init_db()
    with _lock:
        cur = c.execute(sql, params)
        c.commit()
    return cur.lastrowid


def j(obj):
    return json.dumps(obj, ensure_ascii=False)


def uj(text, default=None):
    try:
        return json.loads(text)
    except Exception:
        return default
