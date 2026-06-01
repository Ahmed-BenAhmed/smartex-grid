# SmartGrid ML Handoff

Date: 2026-05-25

This file is for the next machine/agent continuing **Projet 16: prevision de consommation energetique et detection d'anomalies pour smart grid**.

## Current Truth

- `SmartexVR` backend/AI work is separate and handled in the `SmartexVR` repo.
- This repo, `smartex-grid`, is the smart-grid ML project.
- The local demo stack is implemented and runnable without Docker.
- The rigorous ML target is now a benchmark matrix: 30-minute resampling, natural `source` grouping for the demo, rolling-origin forecasting, synthetic true anomaly labels, forecast-residual MAD detection, and model comparison artifacts.
- Prophet is the primary interpretable target model. SeasonalNaive is the deterministic baseline that always runs locally; Prophet, LightGBM, and LSTM Autoencoder are marked unavailable when optional dependencies are missing.

## What Exists

Useful existing files:

- `scripts/prepare_datasets.py` - prepares canonical smart-meter CSVs.
- `scripts/resample_for_model.py` - creates model-ready cadence CSVs.
- `scripts/generate_eda.py` - generates EDA reports and figures.
- `ml/anomaly_detection.py` - CSV/offline rolling median + MAD detector, optional IsolationForest.
- `ml/benchmark_ml.py` - CSV-first benchmark matrix runner.
- `ml/eval_anomaly_detection.py` - evaluates detector flags against synthetic true anomaly labels; supports explicit forecast-residual mode.
- `ml/anomaly_detector.py` - DB-backed residual anomaly detector.
- `ml/prophet_model.py` - DB-backed Prophet training helper.
- `ml/lstm_model.py` - LSTM scaffold.
- `ml/incremental_train.py` - incremental training scaffold.
- `warehouse/schema.sql` and `warehouse/aggregates.sql` - TimescaleDB schema and continuous aggregates.
- `docker-compose.yml` - Kafka, TimescaleDB, Prometheus, Grafana stack.

Canonical processed CSV schema:

```text
time,meter_id,kwh,is_anomaly,source
```

## What Is Still Left

High priority:

1. Install optional ML dependencies in a controlled environment and rerun the benchmark:
   - `prophet`, `pandas` for `prophet_default` and `prophet_tuned`
   - `lightgbm`, `numpy` for `lightgbm_lag_features`
   - `tensorflow`, `numpy` for `lstm_autoencoder`

2. Replace the lightweight `prophet_tuned` placeholder with a real tuning loop:
   - tune changepoint prior, seasonality prior, and seasonality mode
   - keep the same rolling-origin folds and WAPE reporting

3. Add full LightGBM and LSTM Autoencoder runners behind dependency checks.

Medium priority:

- Expand anomaly-type analysis in `reports/ml/anomaly_eval_metrics.json`.
- Update README quickstart with the offline ML demo path.
- Add CI later if desired.

Low priority:

- Optuna tuning.
- More Grafana screenshots.

## Recommended Implementation Shape

Prefer standard-library or light dependencies first. The current environment may not have `pandas`, `numpy`, `sklearn`, or `prophet` installed.

The fastest robust path:

- Use Python standard library CSV parsing for injection/eval.
- Target 30-minute cadence:
  - 24h horizon = 48 forecast steps
  - `group_by=source` for the local demo
  - rolling-origin CV uses at least 5 folds; the local benchmark uses 20 folds to provide contiguous forecast-residual coverage.
- Keep `prophet` optional:
  - try importing `prophet`
  - if unavailable, train/evaluate a seasonal-naive baseline
  - still name output clearly, e.g. `"model_type": "seasonal_naive_fallback"`

Metric definitions:

```text
WAPE = sum(abs(actual - forecast)) / max(sum(abs(actual)), epsilon)
precision = TP / max(TP + FP, 1)
recall = TP / max(TP + FN, 1)
F1 = 2 * precision * recall / max(precision + recall, epsilon)
```

Detection latency:

- For each contiguous injected anomaly window, find first detected anomaly at or after window start and before or shortly after window end.
- Report average latency in samples and minutes if cadence is inferable.

## Acceptance Gate

Before saying the rigorous local benchmark is done, run and record:

```bash
make ml-benchmark-demo
```

Expected artifacts:

```text
data/model_ready/demo_meter_readings_30m.csv
data/model_ready/demo_meter_readings_30m_injected.csv
data/model_ready/demo_meter_readings_30m_injected_forecast_residual_anomalies.csv
reports/ml/forecast_metrics.json
reports/ml/anomaly_eval_metrics.json
reports/ml/experiment_matrix.json
reports/ml/model_comparison.md
reports/ml/ml_demo_summary.md
reports/ml/anomaly_threshold_sweep.svg
```

Minimum success thresholds for the synthetic demo:

```text
forecast WAPE: reported per group and horizon
anomaly Precision/Recall/F1/TP/FP/FN/TN: reported overall, by group, and by injected anomaly type
latency: reported in samples and minutes where cadence is inferable
```

If the real datasets are available, also run:

```bash
make prepare-data
make resample-model
make train-prophet-csv
make inject-anomalies
make eval-anomalies
```

## What Not To Do

- Do not make `SmartexVR` depend on `smartex-grid` runtime services.
- Do not mix textile-machine telemetry into the smart-grid deliverable.
- Do not require Docker/TimescaleDB for the offline ML demo path.
- Do not require Prophet for a passing baseline; keep a fallback path.

## Summary For Pulling On Another Machine

Pull this repo separately from `SmartexVR`:

```bash
git clone git@github.com:Ahmed-BenAhmed/smartex-grid.git
cd smartex-grid
```

Then continue from this file and `docs/what_done_and_left.md`.

The remaining work is specifically the smart-grid ML pipeline: forecast evaluation, anomaly injection, anomaly evaluation, tests, and the offline demo path.
