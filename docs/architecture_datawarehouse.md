# SmartGrid Data Warehouse Architecture

The warehouse schema is defined in `warehouse/schema_v2.sql`; the progressive,
zero-downtime rollout is described in `docs/migration_plan_dw_v2.md`. Mermaid
sources live in `docs/diagrams/dw_*.mmd` and rendered PNGs in
`reports/dw_design/media/`.

---

## 1. Model — star / galaxy with conformed dimensions

A **star / fact-constellation (galaxy)** on a time-series engine (TimescaleDB):
three fact tables share four conformed dimensions. It is **not** a snowflake — no
normalized dimension hierarchies — which keeps joins low for read-heavy dashboards
and ML feature pulls.

```mermaid
graph TB
    classDef dim fill:#EAF8FB,stroke:#22B8C8,color:#102A43;
    classDef fact fill:#FFF4E6,stroke:#F08C00,color:#5C3B00;

    DM["dim_meter (SCD-2)"]:::dim
    DS["dim_source"]:::dim
    DD["dim_date"]:::dim
    DMO["dim_model"]:::dim

    FR["fact_meter_reading<br/>(meter x time)"]:::fact
    FP["fact_prediction<br/>(meter x model x horizon x time)"]:::fact
    FA["fact_anomaly_event<br/>(detection)"]:::fact

    DM --> FR
    DS --> FR
    DD --> FR
    DM --> FP
    DMO --> FP
    DM --> FA
    DMO --> FA
    FR -. "time_bucket" .-> CA["fact_reading_hourly<br/>(continuous aggregate)"]:::fact
```

### Dimensions (`dw`)
| Dimension | Notes |
|---|---|
| `dim_meter` (**SCD-2**) | surrogate `meter_key`, natural `meter_id`, profile, feeder/disco, lat/lon, `valid_from/valid_to/is_current` |
| `dim_source` | dataset origin, country, region, utility/disco |
| `dim_date` | calendar: weekday, month, season, holiday flag, tariff period |
| `dim_model` | model name, version, family, hyperparameters, training run id |

### Facts (`dw`, time-partitioned hypertables, FK → dimensions)
| Fact | Grain |
|---|---|
| `fact_meter_reading` | meter × timestamp — `kwh`, `is_anomaly` |
| `fact_prediction` | meter × model × horizon × timestamp — `kwh_pred`, `kwh_lower`, `kwh_upper` |
| `fact_anomaly_event` | one detection — `kwh_actual`, `kwh_expected`, `deviation`, `severity`, `anomaly_type` |

### Entity-relationship (keys)
```mermaid
erDiagram
    dim_source ||--o{ dim_meter         : "source_key"
    dim_meter  ||--o{ fact_meter_reading : "meter_key"
    dim_source ||--o{ fact_meter_reading : "source_key"
    dim_date   ||--o{ fact_meter_reading : "date_key"
    dim_meter  ||--o{ fact_prediction    : "meter_key"
    dim_model  ||--o{ fact_prediction    : "model_key"
    dim_meter  ||--o{ fact_anomaly_event : "meter_key"
    dim_model  ||--o{ fact_anomaly_event : "model_key"
```

### Physical layer (TimescaleDB)
- Hypertables on every fact (`time` partition, 7-day chunks).
- **Continuous aggregates** (15 m / hourly / daily) over `fact_meter_reading`.
- **Native compression** on chunks older than ~7 days; **retention** policy on raw facts.
- Unique constraints + indexes on `(meter_key, time)` / `(meter_key, model_key, time)`.

---

## 2. Medallion data flow

Bronze (raw) → silver (clean/typed facts + dimensions) → gold (aggregates + marts)
separates ingestion, normalization, and serving.

```mermaid
flowchart LR
    S1["Morocco / London<br/>Nigeria / UCI CSV"] --> K["Kafka<br/>smartgrid.meters.raw"]
    S2["Live replay producer"] --> K
    K --> B["Bronze<br/>raw readings"]
    B --> FR["Silver<br/>fact_meter_reading<br/>(+ dim_meter/source/date)"]
    FR --> CA["Gold<br/>fact_reading_hourly"]
    FR --> ML["ML: forecast + residual MAD"]
    ML --> FP["fact_prediction"]
    ML --> FA["fact_anomaly_event"]
    CA --> G["Grafana"]
    FP --> G
    FA --> G
```

---

## 3. Star vs Snowflake — decision

**Star (chosen).** Smart-grid dimensions are low-cardinality and the workload is
read-heavy (Grafana dashboards + ML feature pulls). Denormalized dimensions mean
fewer joins and faster reads.

**Snowflake (rejected).** Normalizing dimensions into hierarchies
(`meter → location → city → region`) only pays off for very large/redundant
dimensions or strict-normalization governance — neither applies here. It would add
join cost for negligible storage savings.

---

## 4. Progressive rollout (zero downtime)

The model is built in the dedicated `dw` schema; early phases are purely additive,
reads switch only once parity is verified, and consumers are preserved through
identical-column compatibility views. See `docs/migration_plan_dw_v2.md`.

```mermaid
flowchart LR
    P0["Guardrails"] --> P1["Dimensions"] --> P2["Facts + backfill"] --> P3["Dual-write"] --> P4["Repoint reads"] --> P5["Switch to dw views"] --> P6["Cleanup"]
```
