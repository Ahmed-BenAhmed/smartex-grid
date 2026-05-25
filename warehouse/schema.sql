-- ============================================================
-- SmartGrid — TimescaleDB Schema
-- Projet 16: Energy Forecasting & Anomaly Detection
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ── Raw meter readings (15-min granularity) ──────────────────
CREATE TABLE IF NOT EXISTS meter_readings (
    time        TIMESTAMPTZ     NOT NULL,
    meter_id    TEXT            NOT NULL,
    kwh         DOUBLE PRECISION NOT NULL,
    is_anomaly  BOOLEAN         DEFAULT FALSE
);

-- Convert to hypertable partitioned by time (7-day chunks)
SELECT create_hypertable('meter_readings', 'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_meter_readings_meter_id
    ON meter_readings (meter_id, time DESC);

-- ── Household/meter metadata ──────────────────────────────────
CREATE TABLE IF NOT EXISTS meters (
    meter_id    TEXT PRIMARY KEY,
    cluster_id  INT,
    profile     TEXT,
    location    TEXT,
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    installed_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Hourly continuous aggregate ───────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS meter_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', time) AS bucket,
    meter_id,
    SUM(kwh)                    AS kwh_total,
    AVG(kwh)                    AS kwh_avg,
    MAX(kwh)                    AS kwh_max,
    COUNT(*)                    AS reading_count
FROM meter_readings
GROUP BY bucket, meter_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('meter_15min',
    start_offset => INTERVAL '1 day',
    end_offset   => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

-- ── Hourly continuous aggregate ───────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS meter_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    meter_id,
    SUM(kwh)                    AS kwh_total,
    AVG(kwh)                    AS kwh_avg,
    MAX(kwh)                    AS kwh_max,
    COUNT(*)                    AS reading_count
FROM meter_readings
GROUP BY bucket, meter_id
WITH NO DATA;

-- Refresh policy: keep 1 hour lag, refresh every 30 min
SELECT add_continuous_aggregate_policy('meter_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);

-- ── Daily continuous aggregate ────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS meter_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    meter_id,
    SUM(kwh)                   AS kwh_total,
    AVG(kwh)                   AS kwh_avg,
    MAX(kwh)                   AS kwh_peak,
    COUNT(*) FILTER (WHERE is_anomaly) AS anomaly_count
FROM meter_readings
GROUP BY bucket, meter_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('meter_daily',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- ── Model predictions table ───────────────────────────────────
CREATE TABLE IF NOT EXISTS meter_predictions (
    time        TIMESTAMPTZ     NOT NULL,
    meter_id    TEXT            NOT NULL,
    model       TEXT            NOT NULL,  -- 'lstm' or 'prophet'
    kwh_pred    DOUBLE PRECISION NOT NULL,
    kwh_lower   DOUBLE PRECISION,
    kwh_upper   DOUBLE PRECISION
);

SELECT create_hypertable('meter_predictions', 'time',
    if_not_exists => TRUE
);

-- ── Anomaly events table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_events (
    detected_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    meter_id     TEXT            NOT NULL,
    reading_time TIMESTAMPTZ     NOT NULL,
    kwh_actual   DOUBLE PRECISION NOT NULL,
    kwh_expected DOUBLE PRECISION,
    deviation    DOUBLE PRECISION,
    severity     TEXT            CHECK (severity IN ('low', 'medium', 'high'))
);
