What Done And What Left
=======================

Last updated: 2026-05-12

Purpose
-------
Provide a concise status document listing what has been implemented so far and what remains to be done. This is intended as a single-source summary for the ML-focused phase of the project.

What we have done (implemented / available)
-------------------------------------------
- Data normalization & preprocessing
  - scripts/prepare_datasets.py — normalization helpers for Morocco and Nigeria (amp -> kW conversion, canonical schema).
  - scripts/validate_conversion.py — validation utilities for conversion factors.

- Resampling / Model-ready generation
  - scripts/resample_for_model.py — resamples processed CSVs to target cadence (configurable, default hourly). Used to create model-ready files.
  - Example outputs: data/model_ready/*.csv (morocco_meter_readings_60m.csv, nigeria_meter_readings_60m.csv, testsite_meter_readings_60m.csv).

- Anomaly detection (CSV/offline baseline)
  - ml/anomaly_detection.py — NEW: per-group rolling median + MAD detector, optional IsolationForest (runs only when enough samples).
  - ml/anomaly_detector.py — DB-backed residual detector (reads predictions/residuals from DB; requires TimescaleDB).
  - Ran an offline test with synthetic data (data/processed/testsite_meter_readings.csv) → produced anomalies CSV and report under data/model_ready/.

- Forecasting scaffold
  - ml/prophet_model.py — Prophet training helper (reads DB cluster/day aggregates, fits and saves model; example trainer exists).

- Repo snapshot & docs
  - REPO_STATE.md — detailed snapshot of repo state and outputs from this session.
  - docs/project_progress.md — progress notes and diagrams.

What remains (high/medium/low priority)
---------------------------------------
High priority
- Implement Prophet training & evaluation pipeline (ml/train_prophet.py)
  - Rolling-origin CV
  - Save per-group models and validation metrics (WAPE at 1-step and 24h horizons)

- Implement anomaly injection engine (ml/inject_anomalies.py)
  - Supports three types: point anomalies, contextual swaps, trend drift
  - Produce ground-truth y_true for evaluation

- Implement anomaly evaluation harness (ml/eval_anomaly_detection.py)
  - Run detectors on injected datasets and compute Precision/Recall/F1 and detection latency

Medium priority
- Integrate detection baseline with Prophet forecasts (call Prophet from anomaly detector when no precomputed forecasts exist).
- Add Optuna hyperparameter tuning for Prophet (ml/tune_prophet.py) and detector params.
- Add unit tests for injection logic and MAD detector (tests/).

Low priority / Research
- LSTM autoencoder baseline for anomaly detection (ml/lstm_autoencoder.py) — optional research comparison.
- LSTM forecasting baseline for comparison with Prophet.
- CI: add GitHub Actions to run unit tests and linting on push/PR.

Decisions / Conventions (established)
-------------------------------------
- Canonical schema for processed files: time, meter_id, kwh, is_anomaly, source.
- Prefer natural grouping (city/zone/disco/feeder_id/meter_id) for model splits. Clustering is optional and exploratory only.
- Forecast metric: WAPE (Weighted Absolute Percentage Error) — use instead of MAPE.
- Forecast horizon for experiments: 24 hours (at 30-min cadence → 48 steps). Use rolling short-horizon forecasts.
- Anomaly injection types for evaluation: point anomalies, contextual anomalies (segment swaps), trend drift. Inject synthetic positives into clean series to create ground-truth.

Repro / Quick commands
----------------------
- Resample to 30-min cadence:
  python3 smartex-grid/scripts/resample_for_model.py data/processed/<file.csv> --freq-minutes 30

- Detect anomalies on a model-ready CSV (example):
  python3 smartex-grid/ml/anomaly_detection.py smartex-grid/data/model_ready/testsite_meter_readings_60m.csv --group-by meter_id --window 6

Next recommended immediate tasks (pick one to start)
--------------------------------------------------
1) Implement the injection engine (ml/inject_anomalies.py) and run evaluation of current Prophet+MAD detector on injected data.
2) Implement Prophet trainer + rolling-origin CV and compute WAPE baselines per group.
3) Add unit tests for detector and injection code, then enable a simple CI workflow.

Notes / Assumptions
------------------
- TimescaleDB and Docker are not required for the offline pipelines (resample → model-ready CSV → anomaly detection). DB-backed ingestion and scheduled jobs require a running TimescaleDB instance (docker-compose.yml provided).
- If you want I can implement task (1) first (injection + eval) and run it on existing model-ready files (morocco/nigeria) to produce quantitative results.

Contact
-------
If anything needs rephrasing or you want this file added in a different location or with extra details (e.g., owners, ETA), tell me and I'll update.
