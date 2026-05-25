# Project Progress

## Goal

Build a smart-grid pipeline that ingests public energy datasets, normalizes them into a shared schema, stores them in TimescaleDB, and uses them for clustering, forecasting, and anomaly detection.

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
- Produces hourly model-ready CSVs in `data/model_ready/`
- Writes matching metadata JSON per output

## TimescaleDB Changes

- Ingestion loader now auto-discovers all `*_meter_readings.csv` files in `data/processed/`
- Added 15-minute continuous aggregate:
  - `meter_15min`
- Existing aggregates retained:
  - `meter_hourly`
  - `meter_daily`

## ML Pipeline

- `ml/clustering.py` updated to fall back to local CSVs if TimescaleDB is unavailable
- DB updates are optional; cluster assignments can be written locally
- Prophet and LSTM still depend on the Python ML stack and DB access, so they are the next candidates for offline fallback

## Documentation Updated

- `data/README.md`
  - Added Nigeria dataset entry
  - Documented Morocco conversion assumptions and caveats
- `reports/validation/ampere_conversion.md`
- `reports/eda/nigeria_eda.md`

## Current Blockers

- Docker daemon is not reachable in this session, so TimescaleDB ingestion cannot be run here
- The local Python environment is missing some ML packages such as `scikit-learn`, so clustering cannot execute end-to-end in this session

## Recommended Next Steps

1. Add offline CSV fallbacks to `ml/prophet_model.py` and `ml/lstm_model.py`
2. Run clustering on the local model-ready files
3. Start Docker and ingest the processed CSVs into TimescaleDB
4. Refresh continuous aggregates and run anomaly detection
