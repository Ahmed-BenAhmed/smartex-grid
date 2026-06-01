# Migration Plan — Data Warehouse v2 (star/galaxy)

Goal: migrate the whole project from the current lean schema (`warehouse/schema.sql`)
to the conformed-dimension star/galaxy in `warehouse/schema_v2.sql` **without ever
breaking the running system**. At every phase, the existing ingestion, ML, and
Grafana paths keep working.

Strategy: the new model is built **in parallel** in the `dw` schema, backfilled
from `public.*`, then written to in **dual-write** mode, reads are repointed, and
only at the end do the legacy tables become thin **compatibility views** over `dw`.
Each phase is independently reversible.

```
Phase 0   Phase 1     Phase 2      Phase 3       Phase 4      Phase 5       Phase 6
guard  →  dims    →   facts+      → dual-write → repoint    → cutover     → decommission
          (dw)        backfill                  reads         (compat views)
   │         │            │            │            │             │             │
 nothing  additive    additive    writes both   reads dw      legacy = views  drop old
 changes  no impact   no impact   old+new       validated     over dw         (optional)
```

---

## Phase 0 — Guardrails (no changes)
- Tag the current state: `git tag pre-dw-v2`.
- Snapshot data counts for parity checks later:
  `meter_readings`, `meter_predictions`, `anomaly_events`, `meters`, distinct `source`.
- Ensure `make test` is green.

## Phase 1 — Create dimensions (additive, zero impact)
- Run `warehouse/schema_v2.sql` (creates `dw` schema, dims, facts, caggs — all empty).
- Seed dimensions from existing data:
```sql
-- dim_source from existing readings
INSERT INTO dw.dim_source (source_code)
SELECT DISTINCT COALESCE(source,'unknown') FROM public.meter_readings
ON CONFLICT (source_code) DO NOTHING;

-- dim_meter from existing meters + any meter_ids seen in readings
INSERT INTO dw.dim_meter (meter_id, source_key, profile, location, lat, lon)
SELECT m.meter_id, s.source_key, m.profile, m.location, m.lat, m.lon
FROM public.meters m
LEFT JOIN LATERAL (
    SELECT source_key FROM dw.dim_source
    WHERE source_code = (SELECT source FROM public.meter_readings r
                         WHERE r.meter_id = m.meter_id LIMIT 1)
) s ON TRUE
ON CONFLICT DO NOTHING;

-- meter_ids present in readings but absent from public.meters
INSERT INTO dw.dim_meter (meter_id, source_key)
SELECT DISTINCT r.meter_id, ds.source_key
FROM public.meter_readings r
JOIN dw.dim_source ds ON ds.source_code = COALESCE(r.source,'unknown')
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_meter d WHERE d.meter_id = r.meter_id AND d.is_current);

-- dim_model from existing prediction model strings + benchmark models
INSERT INTO dw.dim_model (model_name)
SELECT DISTINCT model FROM public.meter_predictions
ON CONFLICT (model_name, model_version) DO NOTHING;
```
- Reversible: `DROP SCHEMA dw CASCADE;`

## Phase 2 — Build & backfill facts (additive)
- Backfill `dw.fact_meter_reading` from `public.meter_readings`:
```sql
INSERT INTO dw.fact_meter_reading (time, meter_key, source_key, date_key, kwh, is_anomaly)
SELECT r.time,
       dw.get_meter_key(r.meter_id, r.source),
       ds.source_key,
       dw.date_key_of(r.time),
       r.kwh, COALESCE(r.is_anomaly,false)
FROM public.meter_readings r
JOIN dw.dim_source ds ON ds.source_code = COALESCE(r.source,'unknown')
ON CONFLICT (meter_key, time) DO NOTHING;
```
- Backfill `dw.fact_prediction` (map `model` → `model_key`) and `dw.fact_anomaly_event`
  (map `meter_id` → `meter_key`, set `model_key` where known) similarly.
- Refresh the new continuous aggregate:
  `CALL refresh_continuous_aggregate('dw.fact_reading_hourly', NULL, NULL);`
- **Validate parity** (must match Phase 0 snapshot):
```sql
SELECT (SELECT count(*) FROM public.meter_readings)        AS old_readings,
       (SELECT count(*) FROM dw.fact_meter_reading)         AS new_readings;
```
- Reversible: `TRUNCATE dw.fact_* ;` and re-backfill.

## Phase 3 — Dual-write (old path stays primary)
Make writers populate **both** schemas. Old tables remain the source of truth.
- **Ingestion** (`ingestion/kafka_to_timescale.py`): after the existing INSERT into
  `public.meter_readings`, also `INSERT INTO dw.fact_meter_reading` using
  `dw.get_meter_key(meter_id, source)` and `dw.date_key_of(time)`.
  *Lower-touch alternative:* add an `AFTER INSERT` trigger on `public.meter_readings`
  that writes the `dw` row — no app change at all.
- **Forecasts** (`scripts/load_demo_ml_outputs_to_timescale.py`, `ml/*`): also insert
  into `dw.fact_prediction` via `dw.get_model_key(model)`.
- **Anomalies** (`ml/anomaly_detector.py`): also insert into `dw.fact_anomaly_event`.
- Run for a while; confirm `dw` row counts track `public` (lag ≈ 0).
- Reversible: remove the dual-write block / drop the trigger.

## Phase 4 — Repoint reads (validate, still reversible)
- Add **read-only views** that present `dw` in the legacy column shape, under new
  names, and point consumers at them first:
```sql
CREATE OR REPLACE VIEW dw.v_meter_readings AS
SELECT f.time, dm.meter_id, f.kwh, f.is_anomaly, ds.source_code AS source
FROM dw.fact_meter_reading f
JOIN dw.dim_meter dm  ON dm.meter_key = f.meter_key
LEFT JOIN dw.dim_source ds ON ds.source_key = f.source_key;
-- analogous: dw.v_meter_predictions, dw.v_anomaly_events, dw.v_meter_hourly
```
- Point **Grafana** panels (or a second datasource) at `dw.v_*` / `dw.fact_reading_hourly`.
  Compare panel values against the live dashboard. The Grafana SQL stays almost
  identical (same column names).
- Re-run ML reads (`ml/anomaly_detector.py` residual join) against `dw` facts; confirm
  identical detections.
- Reversible: point Grafana/ML back at `public.*`.

## Phase 5 — Cutover (legacy names become compat views)
Once parity holds, flip the source of truth to `dw` and turn the old tables into
**compatibility views** so any untouched code keeps working unchanged:
```sql
BEGIN;
ALTER TABLE public.meter_readings    RENAME TO meter_readings_legacy;
ALTER TABLE public.meter_predictions RENAME TO meter_predictions_legacy;
ALTER TABLE public.anomaly_events    RENAME TO anomaly_events_legacy;

CREATE VIEW public.meter_readings AS SELECT * FROM dw.v_meter_readings;
CREATE VIEW public.meter_predictions AS
  SELECT f.time, dm.meter_id, mm.model_name AS model, f.kwh_pred, f.kwh_lower, f.kwh_upper
  FROM dw.fact_prediction f
  JOIN dw.dim_meter dm ON dm.meter_key = f.meter_key
  JOIN dw.dim_model mm ON mm.model_key = f.model_key;
CREATE VIEW public.anomaly_events AS
  SELECT f.detected_at, dm.meter_id, f.reading_time, f.kwh_actual, f.kwh_expected, f.deviation, f.severity
  FROM dw.fact_anomaly_event f
  JOIN dw.dim_meter dm ON dm.meter_key = f.meter_key;
COMMIT;
```
- Stop the dual-write to legacy tables; writers now target `dw` only (via the
  `get_meter_key`/`get_model_key` helpers). For writes through the old names, add
  `INSTEAD OF INSERT` triggers on the views, or update the writers to target `dw`.
- The current continuous aggregates (`meter_hourly`, ...) are replaced by
  `dw.fact_reading_hourly`; expose `public.meter_hourly` as a view if any query needs it.
- **Rollback:** `DROP VIEW`s and `ALTER TABLE ... RENAME ... _legacy` back to the
  original names — full restore in one transaction.

## Phase 6 — Decommission (optional, after a soak period)
- Once nothing references the `_legacy` tables (verify via logs/`pg_stat`), drop them.
- Replace `make`/runbook references and `docs/` to point at `schema_v2.sql`.
- Keep the `public.*` compat views indefinitely if external tools depend on them.

---

## Code touch-list
| Area | File | Change |
|---|---|---|
| Schema | `warehouse/schema_v2.sql` | new (this PR) |
| Ingestion | `ingestion/kafka_to_timescale.py` | Phase 3 dual-write (or trigger) |
| Bulk load | `ingestion/load_csv_to_timescale.py` | Phase 3 dual-write |
| ML outputs | `scripts/load_demo_ml_outputs_to_timescale.py` | write `dw.fact_prediction` |
| Detector | `ml/anomaly_detector.py` | read/write `dw` facts |
| Dashboards | `grafana/provisioning/...` | Phase 4 repoint to `dw.v_*` |
| Make | `Makefile` | add `dw-init`, `dw-backfill`, `dw-validate` targets |

## Backward-compatibility guarantees
- Phases 1–4 are **purely additive** — `public.*` is untouched, so the current demo,
  Grafana dashboard, and ML scripts keep running exactly as today.
- Phase 5 preserves the **legacy table names as views** with identical columns, so
  code that was never migrated still reads correctly.
- Every phase has an explicit, single-step rollback.
