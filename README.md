# SmartGrid — Energy Forecasting & Anomaly Detection

> **Projet 16** — Prévision de consommation énergétique et détection d'anomalies pour smart grid
> ENSA Berrechid · Ahmed Ben Ahmed

---

## What this project does

| Objective | Implementation |
|---|---|
| Ingest 15-min smart meter time-series | Kafka → TimescaleDB hypertable |
| Data warehouse with hourly/daily granularity | TimescaleDB continuous aggregates |
| Forecast per household cluster | LSTM (TensorFlow) + Prophet per K-Means cluster |
| Detect abnormal consumption peaks | Z-score on model residuals → `anomaly_events` |
| Dashboard with load maps | Grafana (Forecast vs Actual, Anomaly table, Cluster bars) |
| Incremental training | Daily re-train on new data, adaptive time windowing |

---

## Stack

| Layer | Technology |
|---|---|
| Ingestion | **Kafka** (Confluent CP 7.6) |
| Storage | **TimescaleDB** (PostgreSQL 16 extension) |
| ML | **TensorFlow** (LSTM) + **Prophet** |
| Monitoring | **Prometheus** + **Grafana** |
| Orchestration | Docker Compose (standalone) → k8s later |

---

## Quick Start

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

# 5. Cluster meters
make cluster

# 6. Train models (replace 0 with cluster ID)
make train-lstm CLUSTER=0
make train-prophet CLUSTER=0

# 7. Run anomaly detection
make detect
```

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
│   ├── clustering.py       # K-Means on daily load profiles
│   ├── lstm_model.py       # TensorFlow LSTM + adaptive windowing
│   ├── prophet_model.py    # Facebook Prophet
│   ├── anomaly_detector.py # Spike detection via residuals
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
