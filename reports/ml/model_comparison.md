# SmartGrid ML Benchmark Matrix

Target pipeline: `30m resampling -> natural group split -> rolling-origin CV -> forecast benchmark -> synthetic anomaly injection -> residual detectors -> model comparison -> live demo`.

- Input: `data/model_ready/demo_meter_readings_30m.csv`
- Grouping: `source`
- Cadence target: 30 minutes
- Horizon: 24 hours = 48 steps
- Rolling-origin folds: 5

| Model | Family | Status | WAPE 1-step | WAPE 24h horizon | Anomaly F1 | Notes |
|---|---|---|---:|---:|---:|---|
| seasonal_naive | forecast | completed | 0.0971 | 0.1259 | n/a | minimum deterministic baseline |
| prophet_default | forecast | completed | 0.0594 | 2.7628 | n/a | primary interpretable forecasting model |
| prophet_tuned | forecast | completed | 0.0597 | 1.2224 | n/a | Prophet with tuned changepoint/seasonality priors |
| lightgbm_lag_features | forecast | completed | 0.1148 | 0.0707 | n/a | tree baseline with lag and calendar features |
| lstm_autoencoder | sequence_anomaly | completed | n/a | n/a | 0.1933 | research baseline for sequence anomaly detection |

Prophet remains the primary interpretable target model. SeasonalNaive is the guaranteed local baseline; LightGBM and LSTM Autoencoder are research baselines that run only when their dependencies are installed.
