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
  - ml/eval_anomaly_detection.py — evaluates detector outputs against synthetic true anomaly labels, including forecast-residual MAD mode.
  - ml/inject_anomalies.py — injects point spike/drop, contextual segment swap, and trend drift labels.

- Forecasting and benchmark scaffold
  - ml/train_prophet.py — CSV-first rolling-origin WAPE evaluation with optional Prophet and deterministic SeasonalNaive fallback.
  - ml/benchmark_ml.py — writes the rigorous benchmark matrix and model-comparison report.
  - ml/prophet_model.py — DB-backed Prophet helper remains available for live infrastructure work.

- Repo snapshot & docs
  - REPO_STATE.md — detailed snapshot of repo state and outputs from this session.
  - docs/project_progress.md — progress notes and diagrams.

What remains (high/medium/low priority)
---------------------------------------
High priority
- Run and archive the rigorous local gate:
  - `make ml-benchmark-demo`
  - expected artifacts: `reports/ml/forecast_metrics.json`, `reports/ml/anomaly_eval_metrics.json`, `reports/ml/experiment_matrix.json`, `reports/ml/model_comparison.md`, forecast CSVs, injection reports, and threshold sweep plots.

Medium priority
- Add Optuna or grid tuning for Prophet while preserving the same rolling-origin split contract.
- Implement LightGBM lag-feature and LSTM Autoencoder runners behind the benchmark dependency checks.
- Add CI for the unit tests and local ML gate.

Low priority / Research
- More Grafana screenshots and live dashboard evidence.

Decisions / Conventions (established)
-------------------------------------
- Canonical schema for processed files: time, meter_id, kwh, is_anomaly, source.
- Prefer natural grouping (city/zone/disco/feeder_id/meter_id/source) for model splits. Clustering is removed from the main story.
- Forecast metric: WAPE (Weighted Absolute Percentage Error) — use instead of MAPE.
- Forecast horizon for experiments: 24 hours (at 30-min cadence → 48 steps). Use rolling short-horizon forecasts.
- Anomaly injection types for evaluation: point anomalies, contextual day/night segment swaps, sustained trend drift. These are synthetic true anomaly labels; false positives are normal rows flagged by the detector.
- Anomaly detection for the benchmark is forecast-residual based: `forecast -> residual r_t = actual - yhat -> rolling median/MAD -> anomaly flag`.

Repro / Quick commands
----------------------
- Resample to 30-min cadence:
  python3 smartex-grid/scripts/resample_for_model.py data/processed/<file.csv> --freq-minutes 30

- Run the rigorous local benchmark:
  make -C smartex-grid ml-benchmark-demo

- Detect anomalies on a model-ready CSV (example):
  python3 smartex-grid/ml/anomaly_detection.py smartex-grid/data/model_ready/testsite_meter_readings_60m.csv --group-by meter_id --window 6

Next recommended immediate tasks (pick one to start)
--------------------------------------------------
1) Run `make ml-benchmark-demo` and include the generated metrics in the report.
2) Install optional dependencies and rerun Prophet/LightGBM/LSTM matrix entries.
3) Add real Prophet tuning while keeping SeasonalNaive as the always-available baseline.

Notes / Assumptions
------------------
- TimescaleDB and Docker are not required for the offline pipelines (resample → model-ready CSV → anomaly detection). DB-backed ingestion and scheduled jobs require a running TimescaleDB instance (docker-compose.yml provided).

Contact
-------
If anything needs rephrasing or you want this file added in a different location or with extra details (e.g., owners, ETA), tell me and I'll update.
