-- ============================================================
-- Manual refresh / backfill commands
-- Run after initial data load to populate continuous aggregates
-- ============================================================

-- Backfill 15-minute aggregate for last 30 days
CALL refresh_continuous_aggregate('meter_15min',
    NOW() - INTERVAL '30 days', NOW());

-- Backfill hourly aggregate for last 30 days
CALL refresh_continuous_aggregate('meter_hourly',
    NOW() - INTERVAL '30 days', NOW());

-- Backfill daily aggregate for last 30 days
CALL refresh_continuous_aggregate('meter_daily',
    NOW() - INTERVAL '30 days', NOW());

-- ── Useful analytical queries ─────────────────────────────────

-- Top 10 highest-consuming meters today
SELECT meter_id, SUM(kwh_total) AS total_kwh
FROM meter_daily
WHERE bucket = CURRENT_DATE
GROUP BY meter_id
ORDER BY total_kwh DESC
LIMIT 10;

-- Hourly load curve for a specific meter
SELECT bucket, kwh_total
FROM meter_hourly
WHERE meter_id = 'MTR_0001'
  AND bucket >= NOW() - INTERVAL '7 days'
ORDER BY bucket;

-- Anomaly rate per cluster
SELECT m.cluster_id, COUNT(*) AS anomaly_count
FROM anomaly_events ae
JOIN meters m ON ae.meter_id = m.meter_id
WHERE ae.detected_at >= NOW() - INTERVAL '30 days'
GROUP BY m.cluster_id
ORDER BY anomaly_count DESC;
