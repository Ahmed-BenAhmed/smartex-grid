#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/codex-uv}"

FORECAST_CSV="${FORECAST_CSV:-reports/ml/forecasts/demo_meter_readings_30m_lightgbm_lag_features_forecasts.csv}"
ANOMALIES_CSV="${ANOMALIES_CSV:-data/model_ready/demo_meter_readings_30m_injected_forecast_residual_anomalies.csv}"
READINGS_CSV="${READINGS_CSV:-data/processed/demo_meter_readings.csv}"
GRAFANA_URL="http://localhost:3001/d/smartgrid-load-map/smartgrid-e28094-load-map?orgId=1&from=1672531200000&to=1674345600000"

section() {
  printf '\n\033[1;36m[recording-demo]\033[0m %s\n' "$1"
}

require_file() {
  if [[ ! -f "$1" ]]; then
    printf '[recording-demo] missing required file: %s\n' "$1" >&2
    exit 1
  fi
}

wait_http() {
  local name="$1"
  local url="$2"
  for _ in {1..60}; do
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$code" == "200" || "$code" == "302" ]]; then
      printf '[recording-demo] %s -> HTTP %s\n' "$name" "$code"
      return 0
    fi
    sleep 1
  done
  printf '[recording-demo] %s did not become ready: %s\n' "$name" "$url" >&2
  return 1
}

section "checking current report and ML artifacts"
require_file "$FORECAST_CSV"
require_file "$ANOMALIES_CSV"
require_file "$READINGS_CSV"
python -m unittest discover -s tests
typst compile reports/smartgrid_demo/report.typ reports/smartgrid_demo/build/smartgrid_demo_report.pdf

section "starting Docker stack"
docker compose up -d
docker compose ps

section "waiting for TimescaleDB"
for _ in {1..60}; do
  if docker exec grid-timescaledb pg_isready -U smartgrid -d smartgrid >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec grid-timescaledb pg_isready -U smartgrid -d smartgrid

section "preparing Kafka topic and sample messages"
docker exec grid-kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --if-not-exists --topic smartgrid.meters.raw \
  --partitions 1 --replication-factor 1
printf '%s\n' \
  '{"timestamp":"2023-01-21T10:00:00Z","meter_id":"MOROCCO_SOURCE","kwh":1.42,"is_anomaly":false,"source":"morocco_high_resolution"}' \
  '{"timestamp":"2023-01-21T10:15:00Z","meter_id":"LONDON_SOURCE","kwh":3.75,"is_anomaly":true,"source":"london_smart_meters"}' \
  '{"timestamp":"2023-01-21T10:30:00Z","meter_id":"UCI_SOURCE","kwh":0.42,"is_anomaly":false,"source":"uci_household_power"}' \
  | docker exec -i grid-kafka kafka-console-producer \
      --bootstrap-server localhost:9092 \
      --topic smartgrid.meters.raw >/dev/null

section "applying schema and replacing demo rows"
docker exec -i grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 < warehouse/schema.sql
docker exec -i grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 <<'SQL'
DELETE FROM anomaly_events WHERE meter_id IN ('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power');
DELETE FROM meter_predictions WHERE meter_id IN ('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power');
DELETE FROM meter_readings WHERE source IN ('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power');
DELETE FROM meters WHERE meter_id IN ('MOROCCO_SOURCE', 'LONDON_SOURCE', 'NIGERIA_SOURCE', 'UCI_SOURCE');
SQL

section "loading 30-minute readings"
uv run --with psycopg2-binary python ingestion/load_csv_to_timescale.py "$READINGS_CSV"

section "refreshing Timescale aggregates"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 \
  -c "CALL refresh_continuous_aggregate('meter_15min', NULL, NULL);"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 \
  -c "CALL refresh_continuous_aggregate('meter_hourly', NULL, NULL);"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid -v ON_ERROR_STOP=1 \
  -c "CALL refresh_continuous_aggregate('meter_daily', NULL, NULL);"

section "loading forecast and anomaly outputs"
uv run --with psycopg2-binary python scripts/load_demo_ml_outputs_to_timescale.py \
  --forecast-csv "$FORECAST_CSV" \
  --anomalies-csv "$ANOMALIES_CSV"

section "restarting Grafana and Prometheus"
docker compose restart prometheus grafana

section "waiting for recording URLs"
wait_http "Grafana" "http://localhost:3001/api/health"
wait_http "Kafka UI" "http://localhost:8080"
wait_http "Prometheus" "http://localhost:9091/-/ready"

section "verifying full demo stack"
uv run --with psycopg2-binary python scripts/verify_demo_stack.py

section "recording links"
printf 'Report PDF:        %s\n' "$ROOT/reports/smartgrid_demo/build/smartgrid_demo_report.pdf"
printf 'Grafana dashboard: %s\n' "$GRAFANA_URL"
printf 'Kafka UI:          %s\n' "http://localhost:8080"
printf 'Prometheus:        %s\n' "http://localhost:9091/targets"
printf 'ML metrics:        %s\n' "$ROOT/reports/ml/model_comparison.md"
printf 'Demo runbook:      %s\n' "$ROOT/reports/smartgrid_demo/DEMO_RUNBOOK.md"

section "short logs you can show on camera"
docker compose logs --no-color --tail=8 timescaledb kafka kafka-ui prometheus grafana

section "ready"
printf 'Start recording: scroll the PDF first, then open Grafana, Kafka UI, and Prometheus.\n'
