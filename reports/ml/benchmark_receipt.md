# SmartGrid ML Benchmark Receipt

- Run timestamp: 2026-06-01 03:12:58 +01
- Claim: the rigorous local ML layer evaluates 30-minute SmartGrid forecasts and residual anomaly detectors by natural source group.
- Oracle: all models use the same clean 30-minute input, the same injected anomaly labels, `group_by=source`, `horizon_hours=24`, `horizon_steps=48`, and five rolling-origin folds.
- Metrics: WAPE for forecasting; precision, recall, F1, TP/FP/FN/TN, and event latency for anomaly detection.
- Slices: source group, forecast model, detector, anomaly type, row-level labels, event-level labels.
- Baselines: SeasonalNaive, Prophet default, Prophet tuned, LightGBM lag features, LSTM Autoencoder.

## Commands

```sh
make inject-anomalies
env UV_CACHE_DIR=/tmp/codex-uv LD_LIBRARY_PATH=/nix/store/pinksh4wphnmjap99gsqbr6g0ycqpjxh-ld-library-path/share/nix-ld/lib MPLCONFIGDIR=/tmp/codex-mpl LOKY_MAX_CPU_COUNT=10 TF_CPP_MIN_LOG_LEVEL=2 uv run --no-project --python 3.12 --with numpy --with pandas --with prophet --with lightgbm --with scikit-learn --with tensorflow python ml/benchmark_ml.py data/model_ready/demo_meter_readings_30m.csv --group-by source --freq-minutes 30 --horizon-hours 24 --folds 5 --injected-file data/model_ready/demo_meter_readings_30m_injected.csv --lstm-epochs 8
python scripts/compare_anomaly_thresholds.py data/model_ready/demo_meter_readings_30m_injected.csv --group-by source --window 24 --forecast-file reports/ml/forecasts/demo_meter_readings_30m_lightgbm_lag_features_forecasts.csv --min-precision 0.30
python ml/evaluate_anomaly_benchmarks.py data/model_ready/demo_meter_readings_30m_injected.csv --group-by source
python scripts/plot_ml_benchmark.py
python -m unittest discover -s tests
typst compile reports/smartgrid_demo/report.typ reports/smartgrid_demo/build/smartgrid_demo_report.pdf
```

## Results

| Model | WAPE 1-step | WAPE 24h |
|---|---:|---:|
| SeasonalNaive | 0.0971 | 0.1259 |
| Prophet default | 0.0594 | 2.7628 |
| Prophet tuned | 0.0597 | 1.2224 |
| LightGBM lag features | 0.1148 | 0.0707 |

| Detector | Row F1 | Event F1 |
|---|---:|---:|
| SeasonalNaive residual MAD | 0.3472 | 0.4615 |
| Prophet default residual MAD | 0.3881 | 0.4348 |
| Prophet tuned residual MAD | 0.3968 | 0.4762 |
| LightGBM residual MAD | 0.4068 | 0.5000 |
| LSTM Autoencoder | 0.1933 | 0.4727 |

Decision: LightGBM residual MAD is the best operating detector in this synthetic benchmark; Prophet remains the interpretable baseline. Contextual day/night swaps and gradual drift remain intentionally hard cases and are called out in the report.
