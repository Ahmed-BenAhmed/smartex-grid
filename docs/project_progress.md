# Project Progress

## Goal

Build a smart-grid pipeline that ingests public energy datasets, normalizes them into a shared schema, stores them in TimescaleDB, and uses natural source/group splits for forecasting and anomaly detection.

## Canonical Schema

All prepared datasets target:

```csv
time,meter_id,kwh,is_anomaly,source
```

## Datasets Processed

### Morocco

- Source: UCI high-resolution smart meter dataset
- Cities: Marrakech, Laâyoune, Boujdour, Foum Eloued
- Cadence: 30 minutes for Marrakech, 10 minutes for the other cities
- Unit handling:
  - Marrakech: values treated as kW and converted to kWh per interval
  - Other cities: values treated as amperes and converted with `kW = 0.207 × I`
- Output: `data/processed/morocco_meter_readings.csv`
- Notes:
  - Original timestamps are preserved
  - This is an estimated conversion, not a physical measurement

### Nigeria

- Source: Hugging Face mirror of Nigerian Energy & Utilities Household Smart Meter dataset
- Rows: 200,000
- Fields used: `meter_id`, `timestamp`, `consumption_kwh`
- Output: `data/processed/nigeria_meter_readings.csv`
- Metadata: `data/processed/nigeria_metadata.json`
- EDA: `reports/eda/nigeria_eda.md`

### London

- Existing pipeline support preserved
- Dataset documentation updated in `data/README.md`

### UCI Household Power

- Existing pipeline support preserved
- Dataset documentation updated in `data/README.md`

## Validation Work

### Ampere Conversion Check

- Added `scripts/validate_conversion.py`
- Compared Nigeria electrical estimates against the `0.207 kW/A` assumption
- Result:
  - Median inferred factor: `0.2049 kW/A`
  - This supports the Morocco approximation as a reasonable default

## Resampling

- Added `scripts/resample_for_model.py`
- Produces model-ready CSVs in `data/model_ready/`
- The rigorous ML benchmark standardizes on 30-minute cadence, so the 24h horizon is 48 forecast steps.
- Writes matching metadata JSON per output

## TimescaleDB Changes

- Ingestion loader now auto-discovers all `*_meter_readings.csv` files in `data/processed/`
- Added 15-minute continuous aggregate:
  - `meter_15min`
- Existing aggregates retained:
  - `meter_hourly`
  - `meter_daily`

## ML Pipeline

- The main ML story uses natural grouping, not clustering.
- `ml/train_prophet.py` provides CSV-first rolling-origin forecasting with WAPE and an optional Prophet path.
- `ml/benchmark_ml.py` writes the benchmark matrix across SeasonalNaive, Prophet, LightGBM, and LSTM Autoencoder entries.
- `ml/inject_anomalies.py` injects synthetic true anomaly labels: point spike/drop, contextual segment swap, and sustained trend drift.
- `ml/eval_anomaly_detection.py` evaluates forecast-residual MAD flags against synthetic labels with Precision/Recall/F1, confusion counts, anomaly-type breakdowns, and latency.

## Documentation Updated

- `data/README.md`
  - Added Nigeria dataset entry
  - Documented Morocco conversion assumptions and caveats
- `reports/validation/ampere_conversion.md`
- `reports/eda/nigeria_eda.md`

## Current Blockers

- Docker daemon is not reachable in this session, so TimescaleDB ingestion cannot be run here
- The local Python environment is intentionally dependency-light; optional benchmark models are marked unavailable when `prophet`, `lightgbm`, `tensorflow`, `pandas`, or `numpy` are missing.

## Recommended Next Steps

1. Run `make ml-benchmark-demo` and archive the generated `reports/ml/` artifacts.
2. Install optional ML dependencies in a reproducible environment and rerun the matrix.
3. Implement real Prophet tuning and LightGBM/LSTM runners behind the existing dependency checks.
4. Start Docker and ingest the processed CSVs into TimescaleDB for the live dashboard proof.
