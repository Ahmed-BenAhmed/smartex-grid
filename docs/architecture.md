# SmartGrid — Architecture

## Overview

```
Smart Meters (simulator)
        │  15-min readings (JSON)
        ▼
    Kafka  ──────────────────────────────────────────────────────────►  Kafka UI (8080)
        │
        ▼
  kafka_to_timescale.py
        │
        ▼
  TimescaleDB (5432)
  ├── meter_readings     ← raw 15-min hypertable
  ├── meter_hourly       ← continuous aggregate (1h)
  ├── meter_daily        ← continuous aggregate (1d)
  ├── meter_predictions  ← LSTM/Prophet forecasts
  └── anomaly_events     ← detected spikes
        │
        ├──► clustering.py       → assigns meters to K clusters
        ├──► lstm_model.py       → trains LSTM per cluster
        ├──► prophet_model.py    → trains Prophet per cluster
        ├──► anomaly_detector.py → compares actual vs predicted → stores anomalies
        └──► incremental_train.py → daily re-train on new data
        │
        ▼
   Grafana (3001)            Prometheus (9091)
   └── Load Map dashboard    └── Kafka + DB metrics
```

## Link to SmartTex (parent project)

| SmartTex | SmartGrid | Integration path |
|---|---|---|
| `sct013_power` → kW per loom | kWh per smart meter | Add MQTT→Kafka bridge; looms become meters |
| Flink EWMA anomaly | LSTM/Prophet anomaly | Complementary: Flink for real-time, ML for forecasting |
| InfluxDB dashboards | TimescaleDB dashboards | Can be added as separate Grafana datasource |
| Mosquitto MQTT broker | Kafka | MQTT source connector or custom bridge script |

When merging: SmartTex machines expose `power_watts` → bridge to Kafka topic → same pipeline.
