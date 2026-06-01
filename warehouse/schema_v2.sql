-- ============================================================
-- SmartGrid — Target Data Warehouse Schema (v2)
-- Star / galaxy with conformed dimensions on TimescaleDB.
--
-- SAFE TO RUN ALONGSIDE THE CURRENT SCHEMA: every object lives in the
-- dedicated `dw` schema and does not touch public.* (meter_readings, meters,
-- meter_predictions, anomaly_events, continuous aggregates). The migration in
-- docs/migration_plan_dw_v2.md backfills these from the existing tables and adds
-- the public compatibility views at cutover (Phase 5).
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE SCHEMA IF NOT EXISTS dw;

-- ============================================================
-- DIMENSIONS
-- ============================================================

-- ── dim_source ────────────────────────────────────────────────
-- The current free-text `source` becomes a first-class dimension.
CREATE TABLE IF NOT EXISTS dw.dim_source (
    source_key   SERIAL PRIMARY KEY,
    source_code  TEXT NOT NULL UNIQUE,        -- e.g. 'morocco_high_resolution'
    country      TEXT,
    region       TEXT,
    utility      TEXT,                         -- disco / operator
    description  TEXT
);

-- ── dim_model ─────────────────────────────────────────────────
-- Replaces the free-text meter_predictions.model column.
CREATE TABLE IF NOT EXISTS dw.dim_model (
    model_key     SERIAL PRIMARY KEY,
    model_name    TEXT NOT NULL,               -- 'seasonal_naive','prophet_tuned','lightgbm_lag_features',...
    model_version TEXT NOT NULL DEFAULT 'v1',
    family        TEXT,                         -- 'forecast' | 'sequence_anomaly'
    hyperparams   JSONB,
    training_run  TEXT,
    UNIQUE (model_name, model_version)
);

-- ── dim_meter (SCD type 2) ────────────────────────────────────
-- Surrogate key + natural key + validity window so metadata history is kept.
CREATE TABLE IF NOT EXISTS dw.dim_meter (
    meter_key    SERIAL PRIMARY KEY,
    meter_id     TEXT NOT NULL,                -- natural / business key
    source_key   INTEGER REFERENCES dw.dim_source (source_key),
    profile      TEXT,
    feeder       TEXT,
    location     TEXT,
    lat          DOUBLE PRECISION,
    lon          DOUBLE PRECISION,
    valid_from   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to     TIMESTAMPTZ,                  -- NULL = open
    is_current   BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_meter_current
    ON dw.dim_meter (meter_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_dim_meter_id ON dw.dim_meter (meter_id);

-- ── dim_date ──────────────────────────────────────────────────
-- Calendar attributes for forecasting features and BI slicing.
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key     INTEGER PRIMARY KEY,          -- yyyymmdd
    day          DATE NOT NULL UNIQUE,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week  INTEGER NOT NULL,             -- 0=Sunday
    is_weekend   BOOLEAN NOT NULL,
    season       TEXT,
    is_holiday   BOOLEAN NOT NULL DEFAULT FALSE,
    tariff_period TEXT                          -- 'peak' | 'off_peak' | 'shoulder'
);

-- Populate dim_date for a range (idempotent).
INSERT INTO dw.dim_date (date_key, day, year, month, day_of_month, day_of_week, is_weekend, season)
SELECT
    (EXTRACT(YEAR FROM d)*10000 + EXTRACT(MONTH FROM d)*100 + EXTRACT(DAY FROM d))::INT,
    d::DATE,
    EXTRACT(YEAR  FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    EXTRACT(DAY   FROM d)::INT,
    EXTRACT(DOW   FROM d)::INT,
    EXTRACT(DOW   FROM d) IN (0, 6),
    CASE
        WHEN EXTRACT(MONTH FROM d) IN (12, 1, 2)  THEN 'winter'
        WHEN EXTRACT(MONTH FROM d) IN (3, 4, 5)   THEN 'spring'
        WHEN EXTRACT(MONTH FROM d) IN (6, 7, 8)   THEN 'summer'
        ELSE 'autumn'
    END
FROM generate_series('2022-01-01'::DATE, '2027-12-31'::DATE, INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

-- ============================================================
-- FACTS (time-partitioned hypertables, FK to conformed dimensions)
-- ============================================================

-- ── fact_meter_reading ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.fact_meter_reading (
    time        TIMESTAMPTZ      NOT NULL,
    meter_key   INTEGER          NOT NULL REFERENCES dw.dim_meter (meter_key),
    source_key  INTEGER          REFERENCES dw.dim_source (source_key),
    date_key    INTEGER          REFERENCES dw.dim_date (date_key),
    kwh         DOUBLE PRECISION NOT NULL,
    is_anomaly  BOOLEAN          NOT NULL DEFAULT FALSE
);
SELECT create_hypertable('dw.fact_meter_reading', 'time',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_reading
    ON dw.fact_meter_reading (meter_key, time);

-- ── fact_prediction ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.fact_prediction (
    time          TIMESTAMPTZ      NOT NULL,
    meter_key     INTEGER          NOT NULL REFERENCES dw.dim_meter (meter_key),
    model_key     INTEGER          NOT NULL REFERENCES dw.dim_model (model_key),
    horizon_steps INTEGER          NOT NULL DEFAULT 1,
    kwh_pred      DOUBLE PRECISION NOT NULL,
    kwh_lower     DOUBLE PRECISION,
    kwh_upper     DOUBLE PRECISION
);
SELECT create_hypertable('dw.fact_prediction', 'time',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_prediction
    ON dw.fact_prediction (meter_key, model_key, horizon_steps, time);

-- ── fact_anomaly_event ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.fact_anomaly_event (
    reading_time TIMESTAMPTZ      NOT NULL,
    meter_key    INTEGER          NOT NULL REFERENCES dw.dim_meter (meter_key),
    model_key    INTEGER          REFERENCES dw.dim_model (model_key),
    detected_at  TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    kwh_actual   DOUBLE PRECISION NOT NULL,
    kwh_expected DOUBLE PRECISION,
    deviation    DOUBLE PRECISION,
    anomaly_type TEXT,                          -- 'point' | 'contextual' | 'trend_drift'
    severity     TEXT CHECK (severity IN ('low', 'medium', 'high'))
);
SELECT create_hypertable('dw.fact_anomaly_event', 'reading_time',
    chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_fact_anomaly_meter
    ON dw.fact_anomaly_event (meter_key, reading_time DESC);

-- ============================================================
-- GOLD: continuous aggregates over the reading fact
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS dw.fact_reading_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    meter_key,
    SUM(kwh)  AS kwh_total,
    AVG(kwh)  AS kwh_avg,
    MAX(kwh)  AS kwh_max,
    COUNT(*)  AS reading_count,
    COUNT(*) FILTER (WHERE is_anomaly) AS anomaly_count
FROM dw.fact_meter_reading
GROUP BY bucket, meter_key
WITH NO DATA;

SELECT add_continuous_aggregate_policy('dw.fact_reading_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);

-- ============================================================
-- COMPRESSION + RETENTION (telemetry hygiene the current schema lacks)
-- ============================================================
ALTER TABLE dw.fact_meter_reading
    SET (timescaledb.compress, timescaledb.compress_segmentby = 'meter_key');
SELECT add_compression_policy('dw.fact_meter_reading', INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE dw.fact_prediction
    SET (timescaledb.compress, timescaledb.compress_segmentby = 'meter_key, model_key');
SELECT add_compression_policy('dw.fact_prediction', INTERVAL '7 days', if_not_exists => TRUE);

-- Optional raw retention (uncomment to enforce):
-- SELECT add_retention_policy('dw.fact_meter_reading', INTERVAL '400 days', if_not_exists => TRUE);

-- ============================================================
-- UPSERT HELPERS (used by ingestion / ML during dual-write)
-- ============================================================

-- Resolve-or-create a current dim_meter row, return its surrogate key.
CREATE OR REPLACE FUNCTION dw.get_meter_key(p_meter_id TEXT, p_source_code TEXT)
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE v_source_key INT; v_meter_key INT;
BEGIN
    INSERT INTO dw.dim_source (source_code) VALUES (COALESCE(p_source_code,'unknown'))
        ON CONFLICT (source_code) DO NOTHING;
    SELECT source_key INTO v_source_key FROM dw.dim_source WHERE source_code = COALESCE(p_source_code,'unknown');

    SELECT meter_key INTO v_meter_key FROM dw.dim_meter WHERE meter_id = p_meter_id AND is_current;
    IF v_meter_key IS NULL THEN
        INSERT INTO dw.dim_meter (meter_id, source_key) VALUES (p_meter_id, v_source_key)
        RETURNING meter_key INTO v_meter_key;
    END IF;
    RETURN v_meter_key;
END $$;

-- Resolve-or-create a dim_model row, return its surrogate key.
CREATE OR REPLACE FUNCTION dw.get_model_key(p_name TEXT, p_version TEXT DEFAULT 'v1')
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE v_key INT;
BEGIN
    INSERT INTO dw.dim_model (model_name, model_version) VALUES (p_name, COALESCE(p_version,'v1'))
        ON CONFLICT (model_name, model_version) DO NOTHING;
    SELECT model_key INTO v_key FROM dw.dim_model WHERE model_name = p_name AND model_version = COALESCE(p_version,'v1');
    RETURN v_key;
END $$;

-- Convenience: date_key from a timestamp.
CREATE OR REPLACE FUNCTION dw.date_key_of(p_ts TIMESTAMPTZ)
RETURNS INTEGER LANGUAGE sql IMMUTABLE AS $$
    SELECT (EXTRACT(YEAR FROM p_ts)*10000 + EXTRACT(MONTH FROM p_ts)*100 + EXTRACT(DAY FROM p_ts))::INT;
$$;

-- ============================================================
-- NOTE: public.* compatibility views (so existing ingestion / ML / Grafana
-- keep working after cutover) are defined in docs/migration_plan_dw_v2.md,
-- Phase 5 — they are applied only after the legacy tables are renamed.
-- ============================================================
