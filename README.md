# SmartGrid — Energy Forecasting & Anomaly Detection

> **Projet 16** — Prévision de consommation énergétique et détection d'anomalies pour smart grid
> ENSA Berrechid · Ahmed Ben Ahmed

---

## What this project does

| Objective | Implementation |
|---|---|
| Ingest 15-min smart meter time-series | Kafka → TimescaleDB hypertable |
| Data warehouse with hourly/daily granularity | TimescaleDB continuous aggregates |
| Forecast natural source/group loads | SeasonalNaive baseline + Prophet target benchmark |
| Detect abnormal consumption peaks | Forecast residual → rolling median/MAD → anomaly flag |
| Dashboard with load maps | Grafana (Forecast vs Actual, Anomaly table, Cluster bars) |
| Incremental training | Daily re-train on new data, adaptive time windowing |

---

## Stack

| Layer | Technology |
|---|---|
| Ingestion | **Kafka** (Confluent CP 7.6) |
| Storage | **TimescaleDB** (PostgreSQL 16 extension) |
| ML | **Prophet** target + SeasonalNaive baseline; LightGBM/LSTM optional research baselines |
| Monitoring | **Prometheus** + **Grafana** |
| Orchestration | Docker Compose (standalone) → k8s later |

---

## Quick Start

Offline ML benchmark, no Docker or downloads required:

```bash
make ml-benchmark-demo
make test
```

This generates a deterministic 30-minute demo dataset, evaluates a 24h horizon
(48 steps) by natural `source`, injects synthetic true anomaly labels, scores
forecast-residual MAD detection, and writes:

```text
reports/ml/forecast_metrics.json
reports/ml/anomaly_eval_metrics.json
reports/ml/experiment_matrix.json
reports/ml/model_comparison.md
```

Live infrastructure path:

```bash
# 1. Clone and configure
cp .env.example .env
# edit .env with your passwords

# 2. Start infrastructure
make up

# 3. Simulate smart meter data
make simulate

# 4. Start ingestion (Kafka → TimescaleDB)
make ingest

# 5. Train/evaluate forecasts
make train-prophet-csv

# 6. Run anomaly detection
make detect
```

## Datasets

The project starts with the cleaned London Smart Meters dataset from Zenodo
as the main dataset, then uses the UCI household power dataset as a small
test/anomaly-development dataset.

```bash
make download-data
make prepare-data
make load-data
```

This creates local files under `data/raw/` and `data/processed/`. These files
are intentionally ignored by Git because the downloaded datasets are large.

See `data/README.md` for source links, sizes, and the optional REFIT dataset.

Generate EDA reports for London, UCI, and their merged version:

```bash
make eda
```

Reports and figures are written under `reports/eda/`.

**Grafana:** http://localhost:3001
**Kafka UI:** http://localhost:8080
**Prometheus:** http://localhost:9091

---

## Project Structure

```
smartex-grid/
├── simulator/            # Smart meter data generator (15-min readings)
│   └── meter_simulator.py
├── ingestion/            # Kafka consumer → TimescaleDB writer
│   └── kafka_to_timescale.py
├── warehouse/            # DB schema + continuous aggregates
│   ├── schema.sql
│   └── aggregates.sql
├── ml/                   # All ML code
│   ├── benchmark_ml.py     # CSV-first benchmark matrix
│   ├── train_prophet.py    # Rolling-origin WAPE evaluation
│   ├── inject_anomalies.py # Synthetic true anomaly labels
│   ├── eval_anomaly_detection.py # Forecast-residual detector metrics
│   ├── prophet_model.py    # DB-backed Prophet helper
│   ├── lstm_model.py       # TensorFlow LSTM research scaffold
│   ├── anomaly_detector.py # DB-backed spike detection via residuals
│   └── incremental_train.py# Daily re-training
├── grafana/              # Dashboard + datasource provisioning
├── prometheus/           # Scrape config
├── docker-compose.yml
└── docs/architecture.md
```

---

## Link to SmartTex

This project was designed as a standalone course project but shares DNA with
[SmartTex](https://github.com/Ahmed-BenAhmed/smartex) — the Industrial IoT platform for textile machines.

**Key connection:** SmartTex already captures `power_watts` per loom via the `SCT013` current sensor.
In a future integration, each loom becomes a "smart meter" — a MQTT→Kafka bridge is all that's needed
to feed loom power data into this forecasting pipeline.

See [`docs/architecture.md`](docs/architecture.md) for the full integration map.
