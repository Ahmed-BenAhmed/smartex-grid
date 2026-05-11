# SmartGrid — Architecture

## 1. High-Level System Overview

```mermaid
graph TB
    subgraph Sources["Data Sources"]
        SIM["meter_simulator.py\n(15-min synthetic readings)"]
        CSV["Historical CSVs\n(London / UCI datasets)"]
    end

    subgraph Ingestion["Ingestion Layer"]
        KAFKA["Kafka\ntopic: smartgrid.meters.raw"]
        K2T["kafka_to_timescale.py\n(real-time consumer)"]
        LOADER["load_csv_to_timescale.py\n(batch loader)"]
        KAFKAUI["Kafka UI :8080"]
    end

    subgraph Warehouse["Data Warehouse — TimescaleDB :5432"]
        RAW["meter_readings\n(hypertable, 15-min)"]
        AGG1["meter_hourly\n(continuous aggregate)"]
        AGG2["meter_daily\n(continuous aggregate)"]
        PRED["meter_predictions\n(LSTM / Prophet forecasts)"]
        ANOM["anomaly_events\n(detected spikes)"]
        META["meters\n(metadata + cluster_id)"]
    end

    subgraph ML["ML Pipeline"]
        CLUST["clustering.py\n(K-Means, 5 clusters)"]
        LSTM["lstm_model.py\n(LSTM per cluster)"]
        PROPHET["prophet_model.py\n(Prophet per cluster)"]
        DETECT["anomaly_detector.py\n(Z-score on residuals)"]
        INCR["incremental_train.py\n(daily re-fit)"]
    end

    subgraph Monitoring["Monitoring & Dashboards"]
        GRAFANA["Grafana :3001\n(Load Map dashboard)"]
        PROM["Prometheus :9091\n(infra metrics)"]
    end

    SIM -->|JSON stream| KAFKA
    KAFKA --> K2T
    KAFKA --> KAFKAUI
    K2T --> RAW
    CSV --> LOADER --> RAW

    RAW --> AGG1
    RAW --> AGG2
    AGG2 --> CLUST --> META
    RAW --> LSTM --> PRED
    RAW --> PROPHET --> PRED
    PRED --> DETECT --> ANOM
    RAW --> INCR

    RAW --> GRAFANA
    PRED --> GRAFANA
    ANOM --> GRAFANA
    AGG1 --> GRAFANA
    PROM --> GRAFANA
```

---

## 2. Real-Time Data Flow

```mermaid
sequenceDiagram
    participant SIM as meter_simulator.py
    participant KAFKA as Kafka
    participant K2T as kafka_to_timescale.py
    participant DB as TimescaleDB
    participant AGG as Continuous Aggregates
    participant DETECT as anomaly_detector.py
    participant GRAF as Grafana

    loop Every 15 minutes
        SIM->>KAFKA: publish JSON {timestamp, meter_id, kwh, is_anomaly}
        KAFKA->>K2T: consume batch (up to 10 MB)
        K2T->>DB: INSERT INTO meter_readings ON CONFLICT DO NOTHING
        DB->>AGG: auto-refresh meter_hourly (every 30 min)
        DB->>AGG: auto-refresh meter_daily (every 1 hour)
    end

    loop Every hour
        DETECT->>DB: SELECT meter_readings JOIN meter_predictions (last 1h)
        DETECT->>DETECT: compute residuals + rolling Z-score (96-pt window)
        DETECT->>DB: INSERT INTO anomaly_events (severity: low/medium/high)
    end

    GRAF->>DB: SQL queries (TimescaleDB datasource)
    GRAF->>GRAF: render 4 dashboard panels
```

---

## 3. ML Training Pipeline

```mermaid
flowchart TD
    A["meter_daily\n(TimescaleDB)"] -->|last 30 days\n96 time slots × meters| B

    B["clustering.py\nK-Means k=5\nStandardScaler"]
    B -->|cluster_id per meter| C["meters table\ncluster_id updated"]

    C --> D["For each cluster 0..4"]

    D --> E["lstm_model.py\nLoad 90-day history\nper cluster"]
    D --> F["prophet_model.py\nLoad meter_daily aggregates\nper cluster"]

    E --> E1["Window: 96 ticks lookback\n(adaptive 48–288 based on volatility)\nHorizon: 4 ticks (1h)"]
    E1 --> E2["LSTM(64) → LSTM(32) → Dense(4)\n20 epochs, batch 32"]
    E2 --> E3["models/lstm_cluster_{id}.keras"]

    F --> F1["daily_seasonality=True\nweekly + yearly seasonality\nForecast: 7 days ahead"]
    F1 --> F2["models/prophet_cluster_{id}.pkl"]

    E3 --> G["meter_predictions table\n(kwh_pred, kwh_lower, kwh_upper)"]
    F2 --> G

    G --> H["anomaly_detector.py\nActual vs Predicted\nZ-score > 3σ → anomaly_events"]

    I["incremental_train.py\n(runs daily)"] -->|last 24h data per cluster| E2
```

---

## 4. Database Schema

```mermaid
erDiagram
    meters {
        text meter_id PK
        int cluster_id
        text profile
        text location
        float lat
        float lon
    }

    meter_readings {
        timestamptz time PK
        text meter_id PK
        float kwh
        bool is_anomaly
    }

    meter_hourly {
        timestamptz bucket
        text meter_id
        float kwh_total
        float kwh_avg
        float kwh_max
        int reading_count
    }

    meter_daily {
        timestamptz bucket
        text meter_id
        float kwh_total
        float kwh_avg
        float kwh_peak
        int anomaly_count
    }

    meter_predictions {
        timestamptz time
        text meter_id
        text model
        float kwh_pred
        float kwh_lower
        float kwh_upper
    }

    anomaly_events {
        timestamptz detected_at
        text meter_id
        timestamptz reading_time
        float kwh_actual
        float kwh_expected
        float deviation
        text severity
    }

    meters ||--o{ meter_readings : "has readings"
    meters ||--o{ meter_predictions : "has forecasts"
    meters ||--o{ anomaly_events : "has anomalies"
    meter_readings ||--o{ meter_hourly : "rolls up to"
    meter_readings ||--o{ meter_daily : "rolls up to"
    meter_predictions ||--o{ anomaly_events : "compared against"
```

---

## 5. Infrastructure & Container Topology

```mermaid
graph LR
    subgraph Docker["docker-compose stack"]
        direction TB
        TSDB["TimescaleDB\nPostgreSQL 16\n:5432\nVol: timescale_data"]
        ZK["Zookeeper\n:2181"]
        BROKER["Kafka Broker\n:9092\nConfluentCP 7.6"]
        KAFUI["Kafka UI\n:8080"]
        PROM["Prometheus\n:9091\nVol: prometheus_data"]
        GRAF["Grafana 11.3\n:3001\nVol: grafana_data"]
    end

    subgraph Host["Host / Local Python processes"]
        SIM["meter_simulator.py"]
        K2T["kafka_to_timescale.py"]
        ML["ml/ scripts"]
        SCRIPTS["scripts/ (EDA, prepare)"]
    end

    ZK --> BROKER
    BROKER --> KAFUI
    SIM -->|produce| BROKER
    BROKER -->|consume| K2T
    K2T -->|INSERT| TSDB
    ML -->|READ / WRITE| TSDB
    SCRIPTS -->|READ / WRITE| TSDB
    TSDB -->|SQL datasource| GRAF
    PROM -->|metrics datasource| GRAF
    PROM -->|scrape :9092| BROKER
    PROM -->|scrape :5432| TSDB
```

---

## 6. Grafana Dashboard Panels

```mermaid
graph TD
    DB["TimescaleDB"]
    PROM["Prometheus"]

    DB -->|"SELECT time_bucket('1h', time), sum(kwh)\nFROM meter_readings"| P1["Panel 1\nTotal Grid Consumption\n(time series)"]
    DB -->|"SELECT detected_at, meter_id, severity\nFROM anomaly_events ORDER BY detected_at DESC"| P2["Panel 2\nAnomaly Events\n(table)"]
    DB -->|"SELECT c.cluster_id, sum(kwh_total)\nFROM meter_daily JOIN meters"| P3["Panel 3\nConsumption by Cluster\n(bar chart)"]
    DB -->|"SELECT time, kwh_pred, kwh_lower, kwh_upper\nFROM meter_predictions\nJOIN meter_readings"| P4["Panel 4\nForecast vs Actual\n(overlay time series)"]
    PROM --> P5["Panel 5\nInfra Metrics\n(up/down, scrape latency)"]
```

---

## 7. SmartTex Integration Path

```mermaid
graph LR
    subgraph SmartTex["SmartTex (parent project)"]
        LOOM["Textile Loom\n(sct013 power sensor)"]
        MQTT["Mosquitto MQTT"]
        FLINK["Apache Flink\n(EWMA anomaly)"]
        INFLUX["InfluxDB dashboards"]
    end

    subgraph SmartGrid["SmartGrid (this project)"]
        BRIDGE["MQTT→Kafka Bridge\n(to be built)"]
        KAFKA["Kafka\nsmartgrid.meters.raw"]
        TSDB["TimescaleDB\n+ ML pipeline"]
        GRAFANA["Grafana\n(unified dashboard)"]
    end

    LOOM -->|power_watts via MQTT| MQTT
    MQTT -->|topic bridge| BRIDGE
    BRIDGE -->|meter_id = loom_id| KAFKA
    KAFKA --> TSDB
    TSDB --> GRAFANA
    INFLUX -.->|add as 2nd datasource| GRAFANA
    FLINK -.->|real-time alerts| GRAFANA
```

---

## Link to SmartTex (parent project)

| SmartTex | SmartGrid | Integration path |
|---|---|---|
| `sct013_power` → kW per loom | kWh per smart meter | Add MQTT→Kafka bridge; looms become meters |
| Flink EWMA anomaly | LSTM/Prophet anomaly | Complementary: Flink for real-time, ML for forecasting |
| InfluxDB dashboards | TimescaleDB dashboards | Can be added as separate Grafana datasource |
| Mosquitto MQTT broker | Kafka | MQTT source connector or custom bridge script |

When merging: SmartTex machines expose `power_watts` → bridge to Kafka topic → same pipeline.
