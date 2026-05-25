# SmartGrid ML Handoff

Date: 2026-05-25

This file is for the next machine/agent continuing **Projet 16: prevision de consommation energetique et detection d'anomalies pour smart grid**.

## Current Truth

- `SmartexVR` backend/AI work is separate and handled in the `SmartexVR` repo.
- This repo, `smartex-grid`, is the smart-grid ML project.
- The ML completion work here is **not finished yet**.
- The repo currently has preprocessing, EDA reports, Timescale/Kafka/Grafana scaffolding, and baseline ML scripts, but the final quantitative ML pipeline still needs to be implemented and verified.

## What Exists

Useful existing files:

- `scripts/prepare_datasets.py` - prepares canonical smart-meter CSVs.
- `scripts/resample_for_model.py` - creates model-ready cadence CSVs.
- `scripts/generate_eda.py` - generates EDA reports and figures.
- `ml/anomaly_detection.py` - CSV/offline rolling median + MAD detector, optional IsolationForest.
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

1. Add CSV-first Prophet/forecast evaluation:
   - create `ml/train_prophet.py`
   - support model-ready CSV input
   - group by `meter_id` by default
   - implement rolling-origin evaluation
   - output WAPE metrics for one-step and 24h/forecast-horizon evaluation
   - if Prophet is not installed, use a deterministic seasonal-naive fallback so the demo still runs

2. Add anomaly injection:
   - create `ml/inject_anomalies.py`
   - support point spikes/drops
   - support contextual segment swaps
   - support trend drift
   - preserve original schema and write injected `is_anomaly=true` ground truth

3. Add anomaly evaluation:
   - create `ml/eval_anomaly_detection.py`
   - run existing `ml/anomaly_detection.py` or equivalent detector on injected data
   - compute precision, recall, F1
   - compute detection latency where timestamps allow it
   - write report under `reports/ml/`

4. Add a no-download demo path:
   - create a small synthetic smart-meter dataset generator, or add a tiny committed fixture under `tests/fixtures/`
   - make the ML demo runnable without large external datasets
   - recommended Make targets:

```make
demo-data
train-prophet-csv
inject-anomalies
eval-anomalies
ml-demo
test
```

5. Add tests:
   - test anomaly injection marks expected ground truth
   - test MAD detector catches injected spikes
   - test WAPE calculation
   - test forecast fallback works without Prophet installed

Medium priority:

- Save forecast CSVs under `reports/ml/forecasts/`.
- Save metrics JSON/Markdown under `reports/ml/`.
- Integrate forecast residuals into anomaly detection.
- Update README quickstart with the offline ML demo path.
- Add CI later if desired.

Low priority:

- LSTM autoencoder anomaly baseline.
- Optuna tuning.
- More Grafana screenshots.

## Recommended Implementation Shape

Prefer standard-library or light dependencies first. The current environment may not have `pandas`, `numpy`, `sklearn`, or `prophet` installed.

The fastest robust path:

- Use Python standard library CSV parsing for injection/eval.
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

Before saying ML is done, run and record:

```bash
make ml-demo
```

Expected artifacts:

```text
data/model_ready/demo_meter_readings_60m.csv
data/model_ready/demo_meter_readings_60m_injected.csv
data/model_ready/demo_meter_readings_60m_injected_anomalies.csv
reports/ml/forecast_metrics.json
reports/ml/anomaly_eval_metrics.json
reports/ml/ml_demo_summary.md
```

Minimum success thresholds for the synthetic demo:

```text
forecast WAPE: reported, no hard threshold for first baseline
anomaly precision: >= 0.60
anomaly recall: >= 0.60
anomaly F1: >= 0.60
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
