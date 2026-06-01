#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[demo] generating ML demo artifacts"
make ml-demo

echo "[demo] starting Docker stack"
docker compose up -d

echo "[demo] waiting for TimescaleDB"
for _ in {1..60}; do
  if docker exec grid-timescaledb pg_isready -U smartgrid -d smartgrid >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec grid-timescaledb pg_isready -U smartgrid -d smartgrid

echo "[demo] preparing Kafka demo topic"
docker exec grid-kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --if-not-exists --topic smartgrid.meters.raw \
  --partitions 1 --replication-factor 1
printf '%s\n' \
  '{"timestamp":"2023-01-21T10:00:00Z","meter_id":"MOROCCO_SOURCE","kwh":1.42,"is_anomaly":false,"source":"morocco_high_resolution"}' \
  '{"timestamp":"2023-01-21T10:15:00Z","meter_id":"LONDON_SOURCE","kwh":3.75,"is_anomaly":true,"source":"london_smart_meters"}' \
  | docker exec -i grid-kafka kafka-console-producer \
      --bootstrap-server localhost:9092 \
      --topic smartgrid.meters.raw >/dev/null

echo "[demo] applying warehouse schema"
docker exec -i grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 < warehouse/schema.sql

echo "[demo] replacing demo rows"
docker exec -i grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 <<'SQL'
DELETE FROM anomaly_events WHERE meter_id LIKE 'DEMO_METER_%';
DELETE FROM meter_predictions WHERE meter_id LIKE 'DEMO_METER_%';
DELETE FROM meter_readings WHERE meter_id LIKE 'DEMO_METER_%';
DELETE FROM meters WHERE meter_id LIKE 'DEMO_METER_%';
DELETE FROM anomaly_events WHERE meter_id IN ('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power');
DELETE FROM meter_predictions WHERE meter_id IN ('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power');
DELETE FROM meter_readings WHERE source IN ('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power');
DELETE FROM meters WHERE meter_id IN ('MOROCCO_SOURCE', 'LONDON_SOURCE', 'NIGERIA_SOURCE', 'UCI_SOURCE');
SQL

echo "[demo] loading readings"
uv run --with psycopg2-binary python ingestion/load_csv_to_timescale.py \
  data/processed/demo_meter_readings.csv

echo "[demo] refreshing aggregates"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 \
  -c "CALL refresh_continuous_aggregate('meter_15min', NULL, NULL);"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 \
  -c "CALL refresh_continuous_aggregate('meter_hourly', NULL, NULL);"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 \
  -c "CALL refresh_continuous_aggregate('meter_daily', NULL, NULL);"

echo "[demo] loading forecasts and anomaly events"
uv run --with psycopg2-binary python scripts/load_demo_ml_outputs_to_timescale.py

echo "[demo] restarting Grafana and Prometheus so provisioning/config is fresh"
docker compose restart prometheus grafana

echo "[demo] waiting for HTTP services"
for url in http://localhost:3001/api/health http://localhost:8080 http://localhost:9091/-/ready; do
  for _ in {1..60}; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" == "200" || "$code" == "302" ]]; then
      echo "[demo] $url -> $code"
      break
    fi
    sleep 1
  done
done

echo "[demo] verifying stack"
uv run --with psycopg2-binary python scripts/verify_demo_stack.py
