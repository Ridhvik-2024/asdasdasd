-- NAM v2 PostGIS production schema (migration path from the SQLite DAO).
-- Loaded automatically by docker-compose (postgis service initdb.d).
-- The application's db.py keeps a single-file SQLite default for the
-- reference-laptop demo; this schema is the drop-in production layer.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS gazetteer (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT,
  geom GEOMETRY(Point, 4326) NOT NULL,      -- lon east 0-360 stored as -180..180 or 0..360 by convention
  diameter_km DOUBLE PRECISION,
  origin TEXT,
  src TEXT,
  props JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_gazetteer_geom ON gazetteer USING GIST (geom);

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('waypoint','hazard','water','shelter',
                                     'observation','mission','annotation','panorama_pov')),
  geom GEOMETRY(Point, 4326) NOT NULL,
  radius_km DOUBLE PRECISION,
  props JSONB DEFAULT '{}'::jsonb,
  created_by TEXT DEFAULT 'user',
  created TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_nodes_geom ON nodes USING GIST (geom);

CREATE TABLE IF NOT EXISTS missions (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('route','area','evacuation','survey')),
  name TEXT NOT NULL,
  objective TEXT,
  status TEXT DEFAULT 'draft',
  notes TEXT,
  advisory BOOLEAN DEFAULT TRUE,
  created TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mission_stops (
  id BIGSERIAL PRIMARY KEY,
  mission_id TEXT REFERENCES missions(id) ON DELETE CASCADE,
  ord INTEGER NOT NULL,
  geom GEOMETRY(Point, 4326),
  activity TEXT,
  reason TEXT
);

CREATE TABLE IF NOT EXISTS mission_routes (
  id TEXT PRIMARY KEY,
  mission_id TEXT REFERENCES missions(id) ON DELETE CASCADE,
  preset TEXT,
  length_km DOUBLE PRECISION,
  geom GEOMETRY(LineString, 4326),
  stats JSONB DEFAULT '{}'::jsonb,
  created TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bookmarks (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  geom GEOMETRY(Point, 4326),
  camera JSONB DEFAULT '{}'::jsonb,
  created TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS share_links (
  id TEXT PRIMARY KEY,
  payload JSONB NOT NULL,
  created TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_logs (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT now(),
  role TEXT,
  content TEXT
);
