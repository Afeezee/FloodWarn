-- schema.sql — Neon Postgres schema for the FloodWarn risk layer.
--
-- Enable PostGIS (Neon supports it via CREATE EXTENSION), define the
-- risk_points table with a GiST-indexed point geography, and provide
-- one lookup function that the API layer calls.
--
-- Load procedure:
--   1. Provision a Neon database, capture DATABASE_URL.
--   2. psql "$DATABASE_URL" -f db/schema.sql
--   3. python scripts/load_risk_layer.py         (needs DATABASE_URL)
--   4. Verify with:  psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM risk_points;"
--      Expect 144401.

CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS risk_points CASCADE;

CREATE TABLE risk_points (
    id             SERIAL PRIMARY KEY,
    geom           geography(Point, 4326) NOT NULL,
    class          TEXT NOT NULL,
    class_ord      SMALLINT NOT NULL,
    p_no_flood     REAL NOT NULL,
    p_low          REAL NOT NULL,
    p_moderate     REAL NOT NULL,
    p_high         REAL NOT NULL,
    p_very_high    REAL NOT NULL,
    explanation    TEXT NOT NULL,
    top_factors    JSONB NOT NULL
);

CREATE INDEX risk_points_geom_gist ON risk_points USING GIST (geom);
CREATE INDEX risk_points_class     ON risk_points (class_ord);

-- Convenience function used by /api/risk. Returns the nearest point
-- with its distance in metres so the API can decide whether the
-- location is inside the study area's coverage.
CREATE OR REPLACE FUNCTION nearest_risk(lon DOUBLE PRECISION, lat DOUBLE PRECISION)
RETURNS TABLE (
    class       TEXT,
    class_ord   SMALLINT,
    p_no_flood  REAL,
    p_low       REAL,
    p_moderate  REAL,
    p_high      REAL,
    p_very_high REAL,
    explanation TEXT,
    top_factors JSONB,
    distance_m  DOUBLE PRECISION
)
LANGUAGE SQL STABLE AS $$
    SELECT
        r.class,
        r.class_ord,
        r.p_no_flood, r.p_low, r.p_moderate, r.p_high, r.p_very_high,
        r.explanation,
        r.top_factors,
        ST_Distance(r.geom, ST_MakePoint(lon, lat)::geography) AS distance_m
    FROM risk_points r
    ORDER BY r.geom <-> ST_MakePoint(lon, lat)::geography
    LIMIT 1;
$$;
