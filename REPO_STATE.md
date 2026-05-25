Repository Snapshot — Current State
Date: 2026-05-12

Overview
--------
This file documents the current state of the smartex-grid repository (as of the snapshot above).
It focuses on the parts we touched during the session: data preprocessing/resampling, anomaly detection, and the ML roadmap.

High-level goal
---------------
- Build an end-to-end smart-grid pipeline (Ingestion -> Storage -> ML -> Dashboard) that normalizes data to a canonical schema:
  time, meter_id, kwh, is_anomaly, source
- Prefer natural grouping (city/zone/disco/feeder_id/meter_id) instead of mandatory clustering.

What was done in this session
-----------------------------
- Implemented a lightweight anomaly detection module: ml/anomaly_detection.py
  - Rolling robust stats (median + MAD) per-group
  - Optional IsolationForest (runs only for groups with sufficient samples)
- Created a small synthetic processed dataset for testing: data/processed/testsite_meter_readings.csv
- Resampled the synthetic processed data to hourly cadence via scripts/resample_for_model.py
  -> produced data/model_ready/testsite_meter_readings_60m.csv and metadata
- Ran the anomaly detector on the generated CSV and produced:
  - data/model_ready/testsite_meter_readings_60m_anomalies.csv
  - data/model_ready/testsite_meter_readings_60m_anomalies_report.json
- Updated the in-memory todo list to reflect priorities: Prophet as primary forecast baseline, LSTM optional research path, anomaly detection done as a residual-based baseline.

Important files and where to find them
------------------------------------
- Top level / important directories
  - smartex-grid/README.md — project readme and usage notes
  - smartex-grid/docker-compose.yml — local stack (TimescaleDB, Kafka, Grafana, etc.)
  - smartex-grid/scripts/ — preprocessing and dataset utilities
    - resample_for_model.py — resample processed CSVs to fixed cadence (hourly by default)
    - prepare_datasets.py — dataset normalization helpers (Morocco, Nigeria, etc.)
    - validate_conversion.py — conversion validation scripts
  - smartex-grid/ml/ — ML models and training code
    - anomaly_detection.py — NEW: rolling MAD + optional IsolationForest (operates on model-ready CSVs)
    - anomaly_detector.py — DB-backed residual detector (reads predictions from DB)
    - prophet_model.py — Prophet training helper (saves model artifacts)
    - lstm_model.py — LSTM model scaffold (research/optional)
    - clustering.py — exploratory clustering (kept optional)
    - incremental_train.py — incremental training helpers
  - smartex-grid/ingestion/ — ingestion helpers for TimescaleDB/Kafka
    - load_csv_to_timescale.py
    - kafka_to_timescale.py
  - smartex-grid/data/ — data and generated outputs
    - processed/ — processed canonical CSVs
      - testsite_meter_readings.csv (synthetic test data)
      - morocco_meter_readings.csv
      - nigeria_meter_readings.csv
      - nigeria_metadata.json
    - model_ready/ — resampled/aggregated CSVs ready for ML
      - testsite_meter_readings_60m.csv
      - testsite_meter_readings_60m_metadata.json
      - testsite_meter_readings_60m_anomalies.csv
      - testsite_meter_readings_60m_anomalies_report.json
      - morocco_meter_readings_60m.csv
      - morocco_meter_readings_60m_metadata.json
      - nigeria_meter_readings_60m.csv
      - nigeria_meter_readings_60m_metadata.json
  - smartex-grid/docs/ — architecture, diagrams, and progress

Files added/changed in this session
----------------------------------
- Added: smartex-grid/ml/anomaly_detection.py (new detector that operates on CSVs)
- Added: smartex-grid/data/processed/testsite_meter_readings.csv (synthetic test set)
- Created by running: smartex-grid/scripts/resample_for_model.py
  -> smartex-grid/data/model_ready/testsite_meter_readings_60m.csv
  -> smartex-grid/data/model_ready/testsite_meter_readings_60m_metadata.json
- Ran anomaly detection
  -> smartex-grid/data/model_ready/testsite_meter_readings_60m_anomalies.csv
  -> smartex-grid/data/model_ready/testsite_meter_readings_60m_anomalies_report.json

Notes on environment and dependencies
-------------------------------------
- Attempts were made to install scikit-learn, statsmodels and prophet. This environment enforces system-managed Python; I attempted a user install with --break-system-packages. If you run locally, prefer creating a virtualenv or using pipx:
  - python3 -m venv .venv && source .venv/bin/activate && pip install -r ml/requirements.txt
  - or pipx for CLI installs
- TimescaleDB / Docker: during the session the Docker daemon was inaccessible from this environment. The CSV-based offline tests do not require TimescaleDB; DB-backed ingestion, continuous aggregates, and prediction storage require a running TimescaleDB instance (docker-compose.yml provided).

What ran successfully (offline)
------------------------------
1. Resample synthetic processed CSV: (script)
   - Command: python3 smartex-grid/scripts/resample_for_model.py data/processed/testsite_meter_readings.csv --freq-minutes 60
   - Output: data/model_ready/testsite_meter_readings_60m.csv
2. Anomaly detection on model-ready CSV: (script)
   - Command: python3 smartex-grid/ml/anomaly_detection.py smartex-grid/data/model_ready/testsite_meter_readings_60m.csv --group-by meter_id --window 6
   - Outputs:
     - data/model_ready/testsite_meter_readings_60m_anomalies.csv
     - data/model_ready/testsite_meter_readings_60m_anomalies_report.json

Selected snippets / example outputs
---------------------------------
- Anomaly report (summary):
  - METER_A: samples=24, detected=4
  - METER_B: samples=24, detected=3

- Anomalous row example found in CSV:
  - 2023-01-01 12:00:00, METER_A, 10.00000000, is_anomaly=true, source=synthetic

Decisions & recommended default approach (ML)
--------------------------------------------
- Cadence: 30-minute aggregation recommended for your workflow. Current scripts default to hourly but are configurable via resample_for_model.py --freq-minutes.
- Forecasting baseline: Prophet per natural group (city/zone/disco/feeder_id). Use rolling-origin cross-validation and MAE/RMSE as evaluation metrics.
- Anomaly baseline: Forecast-based residual detection using rolling median + MAD with tunable multiplier (3–4). Optionally require persistence over multiple steps to reduce false positives.
- LSTM: keep as an optional research path:
  - LSTM autoencoder for reconstruction-error based anomalies or LSTM forecasting for comparison.
  - Not mandatory unless baseline residual methods fail to capture complex temporal anomalies.

Outstanding tasks / TODO (current priorities)
-----------------------------------------
1. (High) Implement Prophet training + rolling-origin CV script (ml/train_prophet.py) and save per-group models and validation metrics. [pending]
2. (High) Integrate residual-based anomaly detector with Prophet forecasts (update ml/anomaly_detection.py to optionally call Prophet if no predictions provided). [pending]
3. (Medium) Add unit tests for rolling_median_mad_anomalies and anomaly detection behavior. [pending]
4. (Medium) Provide Optuna-based HP tuning for Prophet (optional, improves academic value). [pending]
5. (Low) Implement LSTM autoencoder training (ml/lstm_autoencoder.py) as research baseline. [pending]

How to reproduce the offline test I ran
-------------------------------------
1. Ensure Python 3.9+ available and create a virtualenv:
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r ml/requirements.txt
2. From repo root run:
   python3 smartex-grid/scripts/resample_for_model.py data/processed/testsite_meter_readings.csv --freq-minutes 60
   python3 smartex-grid/ml/anomaly_detection.py smartex-grid/data/model_ready/testsite_meter_readings_60m.csv --group-by meter_id --window 6

Notes and caveats
-----------------
- The repository contains both CSV-based offline tooling and DB-backed ingestion/training code (TimescaleDB integration). The offline path is fully functional in this environment; DB path requires a running TimescaleDB instance.
- Clustering is deliberately optional. Use natural grouping for training and anomaly detection by default.

If you want a different format (plain text, JSON manifest, or a git-tracked release snapshot), tell me which format and I will add it.

End of snapshot
