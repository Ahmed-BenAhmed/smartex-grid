# SmartGrid demo runbook

This runbook reproduces the local SmartGrid evidence used in
`reports/smartgrid_demo/build/smartgrid_demo_report.pdf`.

## 1. Validate code and ML demo

For the recording-friendly full local demo bootstrap, run:

```bash
scripts/recording_demo_flow.sh
```

This is the recommended command for the video because it uses the current 30-minute report artifacts and prints the links/logs to show on camera.

The older bootstrap is still available:

```bash
bash scripts/bootstrap_demo_stack.sh
```

This starts Docker, creates the Kafka demo topic, loads TimescaleDB, loads ML outputs, refreshes Grafana/Prometheus, and runs `scripts/verify_demo_stack.py`.

To run only the ML part:

```bash
make test
make ml-demo
```

Expected ML outputs:

- `reports/ml/forecast_metrics.json`
- `reports/ml/anomaly_eval_metrics.json`
- `reports/ml/ml_demo_summary.md`
- `reports/ml/forecasts/demo_meter_readings_30m_forecasts.csv`
- `reports/ml/forecasts/demo_meter_readings_30m_lightgbm_lag_features_forecasts.csv`
- `data/processed/demo_meter_readings.csv`
- `data/model_ready/demo_meter_readings_30m_injected_forecast_residual_anomalies.csv`

Current demo metrics:

- Best forecast WAPE 24h: `0.0707` with LightGBM lag features
- LightGBM residual-MAD row precision: `0.6316`
- LightGBM residual-MAD row recall: `0.3000`
- LightGBM residual-MAD row F1: `0.4068`
- LightGBM residual-MAD event precision: `0.8571`
- LightGBM residual-MAD event F1: `0.5000`

## 2. Start the local infrastructure

```bash
docker compose up -d
docker compose ps
```

Local services:

- Grafana dashboard: <http://localhost:3001/d/smartgrid-load-map/smartgrid-e28094-load-map?orgId=1&from=1672531200000&to=1674345600000>
- Kafka UI: <http://localhost:8080>
- Prometheus: <http://localhost:9091>
- Kafka broker: `localhost:9092`
- TimescaleDB: `localhost:5432`

Default local credentials:

- Grafana: `admin` / `admin`
- TimescaleDB DSN: `postgresql://smartgrid:smartgrid@localhost:5432/smartgrid`

Grafana also enables anonymous Viewer access in the local Docker demo, so the dashboard link opens directly during presentation. Admin login remains available.

## 3. Load the generated readings into TimescaleDB

```bash
uv run --with psycopg2-binary python ingestion/load_csv_to_timescale.py \
  data/processed/demo_meter_readings.csv

docker exec grid-timescaledb psql -U smartgrid -d smartgrid \
  -c "CALL refresh_continuous_aggregate('meter_15min', NULL, NULL);"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid \
  -c "CALL refresh_continuous_aggregate('meter_hourly', NULL, NULL);"
docker exec grid-timescaledb psql -U smartgrid -d smartgrid \
  -c "CALL refresh_continuous_aggregate('meter_daily', NULL, NULL);"

docker exec grid-timescaledb psql -U smartgrid -d smartgrid -c "
SELECT 'meter_readings' AS table_name, count(*) AS rows FROM meter_readings
UNION ALL SELECT 'meter_hourly', count(*) FROM meter_hourly
UNION ALL SELECT 'meter_daily', count(*) FROM meter_daily
ORDER BY table_name;
SELECT min(time) AS first_reading, max(time) AS last_reading FROM meter_readings;
"
```

Expected counts after a fresh load:

- `meter_readings`: 4032 rows
- `meter_hourly`: 2016 rows
- `meter_daily`: 84 rows
- time range: `2023-01-01 00:00:00+00` to `2023-01-21 23:30:00+00`

Load the forecast and anomaly demo outputs into the Grafana dashboard tables:

```bash
uv run --with psycopg2-binary python scripts/load_demo_ml_outputs_to_timescale.py \
  --forecast-csv reports/ml/forecasts/demo_meter_readings_30m_lightgbm_lag_features_forecasts.csv \
  --anomalies-csv data/model_ready/demo_meter_readings_30m_injected_forecast_residual_anomalies.csv
```

Expected dashboard-table counts:

- `meter_predictions`: 960 rows
- `anomaly_events`: non-zero detected anomalies from the chosen detector output

## 4. Rebuild report evidence and PDF

```bash
python reports/smartgrid_demo/build_evidence_pages.py

for html in reports/smartgrid_demo/evidence/*.html; do
  base=$(basename "$html" .html)
  google-chrome --headless=new --disable-gpu --no-sandbox \
    --window-size=1280,900 \
    --screenshot="reports/smartgrid_demo/screenshots/${base}.png" \
    "file://$(pwd)/$html"
done

google-chrome --headless=new --disable-gpu --no-sandbox \
  --window-size=1365,900 --virtual-time-budget=10000 \
  --run-all-compositor-stages-before-draw \
  --screenshot=reports/smartgrid_demo/screenshots/21_grafana_login.png \
  http://localhost:3001/login

google-chrome --headless=new --disable-gpu --no-sandbox \
  --window-size=1365,900 --virtual-time-budget=10000 \
  --run-all-compositor-stages-before-draw \
  --screenshot=reports/smartgrid_demo/screenshots/22_kafka_ui.png \
  http://localhost:8080

typst compile reports/smartgrid_demo/report.typ \
  reports/smartgrid_demo/build/smartgrid_demo_report.pdf
```

## Notes for the live demo

- The report proves the offline ML path and the local infrastructure path.
- The generated readings are loaded into TimescaleDB and usable by Grafana consumption panels.
- Forecasts and detected anomalies are loaded into `meter_predictions` and `anomaly_events` for the local demo. The next step is to automate that insert in the continuous producer/consumer path.
- `Prometheus` scrapes three live targets: Prometheus itself, Kafka exporter, and TimescaleDB/Postgres exporter.
