# SmartGrid Data Warehouse Architecture

Status: design / target. The current schema (`warehouse/schema.sql`) stays the
source of truth until the migration in `docs/migration_plan_dw_v2.md` completes.
The target schema lives in `warehouse/schema_v2.sql`.

---

## 1. Current architecture (`warehouse/schema.sql`)

A lean **star / fact-constellation (galaxy)** layered on a **time-series engine**
(TimescaleDB). It is *not* a snowflake — no normalized dimension hierarchies.

| Object | Role | Grain |
|---|---|---|
| `meter_readings` (hypertable, 7-day chunks) | Fact | reading / meter / timestamp |
| `meter_predictions` (hypertable) | Fact | forecast / meter / model / timestamp |
| `anomaly_events` | Fact | one detection event |
| `meters` (PK `meter_id`) | Dimension | one row / meter |
| `meter_15min` / `meter_hourly` / `meter_daily` (continuous aggregates) | Rollup / OLAP layer | time-bucketed summaries |

```
                 ┌───────────────┐
                 │    meters     │   (the only real dimension)
                 │  dim_meter*   │
                 └──────┬────────┘
                        │ meter_id (not enforced)
      ┌─────────────────┼─────────────────┐
      ▼                 ▼                 ▼
┌────────────┐   ┌───────────────┐  ┌────────────────┐
│meter_read- │   │meter_predic-  │  │ anomaly_events │   ← fact constellation
│ings (fact) │   │tions (fact)   │  │   (fact)       │
└─────┬──────┘   └───────────────┘  └────────────────┘
      │ time_bucket rollups
      ▼
┌──────────────────────────────────────────┐
│ meter_15min / meter_hourly / meter_daily  │  ← continuous aggregates (cube)
└──────────────────────────────────────────┘
```

### Gaps vs a real dimensional model
- `source` is a **degenerate dimension** (free text in the fact), not `dim_source`.
- **No date dimension** — only `TIMESTAMPTZ`; calendar features (holiday, season, tariff window) are unavailable for ML/BI.
- **No foreign keys / surrogate keys** — `meter_readings.meter_id` is not enforced against `meters`.
- `meter_predictions.model` is **free text** instead of `dim_model` (name/version/hyperparams).
- `meters` has **no SCD** — metadata changes overwrite history.
- `anomaly_events` is not a hypertable and is unindexed; facts lack uniqueness constraints (dup risk; the detector joins on `(meter_id, time)`).
- No native **compression / retention** policies (costly for telemetry at scale).

---

## 2. Target architecture

Keep the time-series facts (correct for telemetry) and formalize a
**star / galaxy with conformed dimensions**, organized in **medallion layers**.
New objects live in a dedicated `dw` schema so `public.*` keeps working.

```
Kafka ─▶ bronze (raw, append-only) ─▶ silver (clean, typed) ─▶ gold (facts + aggregates + marts)
```

### Dimensions (`dw`)
| Dimension | Notes |
|---|---|
| `dim_meter` (**SCD-2**) | surrogate `meter_key`, natural `meter_id`, profile, feeder/disco, lat/lon, `valid_from/valid_to/is_current` |
| `dim_source` | dataset origin, country, region, utility/disco |
| `dim_date` | calendar: weekday, month, season, holiday flag, tariff period |
| `dim_model` | model name, version, hyperparameters, training run id |

### Facts (`dw`, time-partitioned hypertables, FK → dimensions)
| Fact | Grain |
|---|---|
| `fact_meter_reading` | meter × timestamp |
| `fact_prediction` | meter × model × horizon × timestamp |
| `fact_anomaly_event` | one detection |

```
        dim_date ─┐      ┌─ dim_source
                  ▼      ▼
              ┌───────────────────┐
   dim_meter ▶│ fact_meter_reading│
      │       └───────────────────┘
      │       ┌───────────────────┐
      ├──────▶│  fact_prediction  │◀── dim_model
      │       └───────────────────┘
      │       ┌───────────────────┐
      └──────▶│ fact_anomaly_event│
              └───────────────────┘
   (conformed dimensions shared across all facts = galaxy schema)
```

### Physical layer (TimescaleDB)
- Hypertables on every fact (`time` partition, 7-day chunks).
- **Continuous aggregates** (15 m / hourly / daily) rebuilt over `fact_meter_reading`.
- **Native compression** on chunks older than ~7 days; **retention** policy on raw facts.
- Unique constraints + indexes on `(meter_key, time)` / `(meter_key, model_key, time)`.

---

## 3. Star vs Snowflake — decision

**Star (chosen).** Smart-grid dimensions are low-cardinality and the workload is
read-heavy (Grafana dashboards + ML feature pulls). Denormalized dimensions mean
fewer joins and faster reads.

**Snowflake (rejected).** Normalizing dimensions into hierarchies
(`meter → location → city → region`) only pays off for very large/redundant
dimensions or strict-normalization governance — neither applies here. It would add
join cost for negligible storage savings.

> Net: the current design is an **under-modeled star/galaxy on Timescale**; the
> target keeps the time-series facts and adds **conformed dimensions
> (dim_meter SCD-2, dim_source, dim_date, dim_model) + compression/retention +
> medallion layering**. Snowflaking would be a regression for these query patterns.

See `docs/migration_plan_dw_v2.md` for the non-breaking, phased migration.
