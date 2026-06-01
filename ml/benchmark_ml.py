"""Rigorous CSV-first SmartGrid ML benchmark matrix.

The fast local environment is intentionally dependency-light. This harness runs
every available baseline through the same grouped rolling-origin forecast split
and records unavailable research baselines with explicit dependency evidence.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from eval_anomaly_detection import (
    bool_value,
    confusion,
    confusion_by_anomaly_type,
    event_detection_metrics,
    event_metrics_by_type,
    infer_cadence_minutes as infer_eval_cadence_minutes,
    latency_stats,
    parse_time as parse_eval_time,
)
from train_prophet import (
    FORECAST_DIR,
    REPORT_DIR,
    choose_cutoffs,
    evaluate_group,
    horizon_steps,
    infer_cadence_minutes,
    read_grouped_csv,
    relative,
    wape,
    write_forecasts,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "model_ready" / "demo_meter_readings_30m.csv"
MATRIX_PATH = REPORT_DIR / "experiment_matrix.json"
COMPARISON_PATH = REPORT_DIR / "model_comparison.md"
FORECAST_METRICS_PATH = REPORT_DIR / "forecast_metrics.json"
LSTM_AE_METRICS_PATH = REPORT_DIR / "lstm_autoencoder_eval_metrics.json"


def dependency_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_").lower()


def model_specs() -> list[dict]:
    return [
        {
            "name": "seasonal_naive",
            "family": "forecast",
            "runner": "seasonal_naive",
            "required_modules": [],
            "role": "minimum deterministic baseline",
        },
        {
            "name": "prophet_default",
            "family": "forecast",
            "runner": "prophet",
            "required_modules": ["prophet", "pandas"],
            "role": "primary interpretable forecasting model",
        },
        {
            "name": "prophet_tuned",
            "family": "forecast",
            "runner": "prophet_tuned",
            "required_modules": ["prophet", "pandas"],
            "role": "Prophet with tuned changepoint/seasonality priors",
            "tuning_note": "Uses the same split contract; lightweight demo marks it unavailable when Prophet is absent.",
        },
        {
            "name": "lightgbm_lag_features",
            "family": "forecast",
            "runner": "lightgbm",
            "required_modules": ["lightgbm", "numpy", "sklearn"],
            "role": "tree baseline with lag and calendar features",
        },
        {
            "name": "lstm_autoencoder",
            "family": "sequence_anomaly",
            "runner": "lstm_autoencoder",
            "required_modules": ["tensorflow", "numpy"],
            "role": "research baseline for sequence anomaly detection",
        },
    ]


def unavailable_reason(required_modules: Sequence[str]) -> str | None:
    missing = [module for module in required_modules if not dependency_available(module)]
    if missing:
        return "missing Python module(s): " + ", ".join(missing)
    return None


def aggregate_metrics(group_metrics: Sequence[dict], forecast_rows: Sequence[dict]) -> dict:
    one_actual = [float(row["actual"]) for row in forecast_rows if int(row["horizon_step"]) == 1]
    one_forecast = [float(row["forecast"]) for row in forecast_rows if int(row["horizon_step"]) == 1]
    all_actual = [float(row["actual"]) for row in forecast_rows]
    all_forecast = [float(row["forecast"]) for row in forecast_rows]
    return {
        "groups": len(group_metrics),
        "forecast_rows": len(forecast_rows),
        "wape_1_step": wape(one_actual, one_forecast) if one_actual else math.nan,
        "wape_horizon": wape(all_actual, all_forecast) if all_actual else math.nan,
    }


def calendar_features(times: Sequence, target_idx: int) -> list[float]:
    import math

    ts = times[target_idx]
    hour = ts.hour + ts.minute / 60.0
    dow = ts.weekday()
    return [
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        math.sin(2 * math.pi * dow / 7),
        math.cos(2 * math.pi * dow / 7),
    ]


def lag_feature_row(history: Sequence[float], times: Sequence, target_idx: int, daily_steps: int, weekly_steps: int) -> list[float]:
    lags = [1, 2, daily_steps, daily_steps * 2, weekly_steps]
    row = [float(history[target_idx - lag]) for lag in lags]
    daily_window = history[target_idx - daily_steps : target_idx]
    recent_window = history[target_idx - 6 : target_idx]
    row.extend(
        [
            float(sum(daily_window) / len(daily_window)),
            float(sum(recent_window) / len(recent_window)),
        ]
    )
    row.extend(calendar_features(times, target_idx))
    return row


def lightgbm_forecast_group(
    group_key: str,
    series: Sequence[Tuple],
    horizon_hours: int,
    folds: int,
) -> tuple[list[dict], dict]:
    import lightgbm as lgb

    times = [item[0] for item in series]
    values = [item[1] for item in series]
    cadence = infer_cadence_minutes(times)
    horizon = horizon_steps(horizon_hours, cadence)
    daily_steps = horizon_steps(24, cadence)
    weekly_steps = daily_steps * 7
    max_lag = min(weekly_steps, max(daily_steps * 2, 2))
    start = max(max_lag + daily_steps, horizon)
    cutoffs = choose_cutoffs(len(values), start=start, horizon=horizon, folds=folds)

    forecast_rows: list[dict] = []
    one_actual: list[float] = []
    one_forecast: list[float] = []
    horizon_actual: list[float] = []
    horizon_forecast: list[float] = []

    for fold_idx, cutoff in enumerate(cutoffs, start=1):
        X = []
        y = []
        for target_idx in range(max_lag, cutoff):
            X.append(lag_feature_row(values, times, target_idx, daily_steps, max_lag))
            y.append(float(values[target_idx]))
        model = lgb.LGBMRegressor(
            n_estimators=80,
            learning_rate=0.05,
            num_leaves=15,
            objective="regression_l1",
            random_state=42,
            verbosity=-1,
        )
        import numpy as np

        model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float))

        history = list(values[: cutoff + horizon])
        preds = []
        for target_idx in range(cutoff, cutoff + horizon):
            features = lag_feature_row(history, times, target_idx, daily_steps, max_lag)
            pred = max(0.0, float(model.predict(np.asarray([features], dtype=float))[0]))
            history[target_idx] = pred
            preds.append(pred)

        actuals = values[cutoff : cutoff + horizon]
        target_times = times[cutoff : cutoff + horizon]
        for step, (target_time, actual, pred) in enumerate(zip(target_times, actuals, preds), start=1):
            forecast_rows.append(
                {
                    "group_key": group_key,
                    "fold": fold_idx,
                    "horizon_step": step,
                    "time": target_time.isoformat(sep=" "),
                    "actual": f"{actual:.8f}",
                    "forecast": f"{pred:.8f}",
                    "model_type": "lightgbm_lag_features",
                }
            )
        if actuals and preds:
            one_actual.append(actuals[0])
            one_forecast.append(preds[0])
            horizon_actual.extend(actuals)
            horizon_forecast.extend(preds)

    metrics = {
        "group_key": group_key,
        "samples": len(values),
        "cadence_minutes": cadence,
        "horizon_hours": horizon_hours,
        "horizon_steps": horizon,
        "folds_requested": folds,
        "folds_used": len(cutoffs),
        "model_type": "lightgbm_lag_features",
        "model_name": "lightgbm_lag_features",
        "wape_1_step": wape(one_actual, one_forecast) if one_actual else math.nan,
        "wape_horizon": wape(horizon_actual, horizon_forecast) if horizon_actual else math.nan,
    }
    return forecast_rows, metrics


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def grouped_values(rows: Sequence[dict], group_by: str) -> dict[str, list[tuple]]:
    groups: dict[str, list[tuple]] = {}
    for idx, row in enumerate(rows):
        groups.setdefault(row[group_by], []).append((parse_eval_time(row["time"]), float(row["kwh"]), idx))
    return {key: sorted(values, key=lambda item: item[0]) for key, values in groups.items()}


def sequence_windows(values, window: int):
    import numpy as np

    if len(values) < window:
        return np.empty((0, window, 1), dtype="float32")
    return np.asarray([values[idx - window : idx] for idx in range(window, len(values) + 1)], dtype="float32").reshape(-1, window, 1)


def median_mad_threshold(values, multiplier: float) -> float:
    import numpy as np

    if len(values) == 0:
        return math.inf
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med)))
    return med + multiplier * max(mad, 1e-9)


def train_lstm_autoencoder(train_values, window: int, epochs: int, seed: int):
    import numpy as np
    import tensorflow as tf

    tf.keras.utils.set_random_seed(seed)
    normalized = np.asarray(train_values, dtype="float32")
    mean = float(np.mean(normalized))
    std = float(np.std(normalized) or 1.0)
    normalized = (normalized - mean) / std
    X = sequence_windows(normalized, window)
    if len(X) < 8:
        raise ValueError("not enough windows for LSTM autoencoder training")

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(window, 1)),
            tf.keras.layers.LSTM(16, activation="tanh"),
            tf.keras.layers.RepeatVector(window),
            tf.keras.layers.LSTM(16, activation="tanh", return_sequences=True),
            tf.keras.layers.TimeDistributed(tf.keras.layers.Dense(1)),
        ]
    )
    model.compile(optimizer="adam", loss="mae")
    model.fit(X, X, epochs=epochs, batch_size=32, verbose=0, shuffle=False)
    reconstruction = model.predict(X, verbose=0)
    train_errors = np.mean(np.abs(reconstruction - X), axis=(1, 2))
    return model, mean, std, train_errors


def lstm_autoencoder_scores(model, values, mean: float, std: float, window: int):
    import numpy as np

    normalized = (np.asarray(values, dtype="float32") - mean) / std
    X = sequence_windows(normalized, window)
    scores = [0.0] * len(values)
    if len(X) == 0:
        return scores
    reconstruction = model.predict(X, verbose=0)
    errors = np.mean(np.abs(reconstruction - X), axis=(1, 2))
    for end_idx, error in enumerate(errors, start=window - 1):
        scores[end_idx] = float(error)
    return scores


def write_lstm_predictions(path: Path, rows: Sequence[dict], fieldnames: Sequence[str], flags: Sequence[bool], scores: Sequence[float]) -> None:
    out_fields = list(fieldnames)
    for field in ["lstm_ae_score", "lstm_ae_threshold"]:
        if field not in out_fields:
            out_fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=out_fields)
        writer.writeheader()
        for row, flag, score in zip(rows, flags, scores):
            row_out = dict(row)
            row_out["is_anomaly"] = "true" if flag else "false"
            row_out["lstm_ae_score"] = f"{score:.8f}"
            row_out.setdefault("lstm_ae_threshold", "")
            writer.writerow(row_out)


def run_lstm_autoencoder(input_path: Path, injected_path: Path, group_by: str, spec: dict, window: int, epochs: int) -> dict:
    clean_groups = read_grouped_csv(input_path, group_by)
    injected_rows, fieldnames = read_rows(injected_path)
    if group_by not in fieldnames:
        raise ValueError(f"group_by column '{group_by}' not found in {injected_path}")
    injected_groups = grouped_values(injected_rows, group_by)

    all_truth: list[bool] = []
    all_pred: list[bool] = []
    all_types: list[str] = []
    all_scores = [0.0] * len(injected_rows)
    all_flags = [False] * len(injected_rows)
    group_payload = {}

    for group_key, clean_series in sorted(clean_groups.items()):
        if group_key not in injected_groups:
            continue
        train_values = [value for _time_value, value in clean_series]
        model, mean, std, train_errors = train_lstm_autoencoder(train_values, window, epochs, seed=42)
        threshold = median_mad_threshold(train_errors, multiplier=4.0)
        injected_series = injected_groups[group_key]
        times = [time_value for time_value, _value, _idx in injected_series]
        values = [value for _time_value, value, _idx in injected_series]
        indices = [idx for _time_value, _value, idx in injected_series]
        scores = lstm_autoencoder_scores(model, values, mean, std, window)
        pred_flags = [idx >= window - 1 and score > threshold for idx, score in enumerate(scores)]

        truth_flags = [bool_value(injected_rows[idx].get("is_anomaly", "false")) for idx in indices]
        anomaly_types = [injected_rows[idx].get("anomaly_type", "") for idx in indices]
        for row_idx, score, flag in zip(indices, scores, pred_flags):
            all_scores[row_idx] = score
            all_flags[row_idx] = flag
            injected_rows[row_idx]["lstm_ae_threshold"] = f"{threshold:.8f}"
        all_truth.extend(truth_flags)
        all_pred.extend(pred_flags)
        all_types.extend(anomaly_types)
        group_payload[group_key] = {
            **confusion(truth_flags, pred_flags),
            **latency_stats(times, truth_flags, pred_flags, tolerance_steps=2),
            "by_anomaly_type": confusion_by_anomaly_type(truth_flags, pred_flags, anomaly_types),
            "event_level": event_detection_metrics(truth_flags, pred_flags, anomaly_types, 2, 5, 1),
            "event_level_by_anomaly_type": event_metrics_by_type(truth_flags, pred_flags, anomaly_types, 2, 5, 1),
            "threshold": threshold,
            "train_windows": len(train_errors),
            "evaluated_rows": len(truth_flags),
        }

    prediction_path = injected_path.with_name(injected_path.stem + "_lstm_autoencoder_anomalies.csv")
    write_lstm_predictions(prediction_path, injected_rows, fieldnames, all_flags, all_scores)

    payload = {
        "name": spec["name"],
        "family": spec["family"],
        "status": "completed",
        "role": spec["role"],
        "input_file": relative(input_path),
        "injected_file": relative(injected_path),
        "prediction_file": relative(prediction_path),
        "detector": "lstm_autoencoder_reconstruction",
        "group_by": group_by,
        "window": window,
        "epochs": epochs,
        "overall": confusion(all_truth, all_pred),
        "by_anomaly_type": confusion_by_anomaly_type(all_truth, all_pred, all_types),
        "event_level": event_detection_metrics(all_truth, all_pred, all_types, 2, 5, 1),
        "event_level_by_anomaly_type": event_metrics_by_type(all_truth, all_pred, all_types, 2, 5, 1),
        "event_scoring": {
            "event_min_flags": 5,
            "event_min_consecutive": 1,
            "point_events_override_min_flags": 1,
        },
        "groups": group_payload,
    }
    LSTM_AE_METRICS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=True), encoding="utf-8")
    return payload


def run_forecast_model(input_path: Path, group_by: str, horizon_hours: int, folds: int, spec: dict) -> dict:
    groups = read_grouped_csv(input_path, group_by)
    all_forecasts: List[dict] = []
    group_metrics: List[dict] = []
    model_arg = spec["runner"]
    for group_key, series in sorted(groups.items()):
        if model_arg == "lightgbm":
            forecasts, metrics = lightgbm_forecast_group(group_key, series, horizon_hours, folds)
        else:
            forecasts, metrics = evaluate_group(group_key, series, model_arg, horizon_hours, folds)
            for row in forecasts:
                row["model_type"] = spec["name"] if row["model_type"] == "seasonal_naive_fallback" else row["model_type"]
        metrics["model_name"] = spec["name"]
        all_forecasts.extend(forecasts)
        group_metrics.append(metrics)

    forecast_path = FORECAST_DIR / f"{input_path.stem}_{safe_name(spec['name'])}_forecasts.csv"
    write_forecasts(forecast_path, all_forecasts)
    if spec["name"] == "seasonal_naive":
        write_forecasts(FORECAST_DIR / f"{input_path.stem}_forecasts.csv", all_forecasts)
    return {
        "name": spec["name"],
        "family": spec["family"],
        "status": "completed",
        "role": spec["role"],
        "forecast_file": relative(forecast_path),
        "groups": group_metrics,
        "overall": aggregate_metrics(group_metrics, all_forecasts),
    }


def write_matrix(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=True), encoding="utf-8")


def format_score(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "n/a"
    return f"{value:.4f}"


def write_comparison(path: Path, payload: dict) -> None:
    lines = [
        "# SmartGrid ML Benchmark Matrix",
        "",
        "Target pipeline: `30m resampling -> natural group split -> rolling-origin CV -> forecast benchmark -> synthetic anomaly injection -> residual detectors -> model comparison -> live demo`.",
        "",
        f"- Input: `{payload['input_file']}`",
        f"- Grouping: `{payload['group_by']}`",
        f"- Cadence target: {payload['freq_minutes']} minutes",
        f"- Horizon: {payload['horizon_hours']} hours = {payload['horizon_steps']} steps",
        f"- Rolling-origin folds: {payload['folds']}",
        "",
        "| Model | Family | Status | WAPE 1-step | WAPE 24h horizon | Anomaly F1 | Notes |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for item in payload["experiments"]:
        overall = item.get("overall", {})
        notes = item.get("unavailable_reason") or item.get("role", "")
        anomaly_f1 = item.get("overall", {}).get("f1") if item.get("family") == "sequence_anomaly" else None
        lines.append(
            "| "
            f"{item['name']} | "
            f"{item['family']} | "
            f"{item['status']} | "
            f"{format_score(overall.get('wape_1_step'))} | "
            f"{format_score(overall.get('wape_horizon'))} | "
            f"{format_score(anomaly_f1)} | "
            f"{notes} |"
        )
    lines.extend(
        [
            "",
            "Prophet remains the primary interpretable target model. SeasonalNaive is the guaranteed local baseline; LightGBM and LSTM Autoencoder are research baselines that run only when their dependencies are installed.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_canonical_forecast_metrics(path: Path, payload: dict) -> None:
    completed_forecasts = [item for item in payload["experiments"] if item["family"] == "forecast" and item["status"] == "completed"]
    primary = next((item for item in completed_forecasts if item["name"].startswith("prophet")), None)
    primary = primary or next((item for item in completed_forecasts if item["name"] == "seasonal_naive"), None)
    output = {
        "input_file": payload["input_file"],
        "group_by": payload["group_by"],
        "freq_minutes": payload["freq_minutes"],
        "horizon_hours": payload["horizon_hours"],
        "horizon_steps": payload["horizon_steps"],
        "folds": payload["folds"],
        "primary_model": primary["name"] if primary else None,
        "primary_forecast_file": primary.get("forecast_file") if primary else None,
        "models": completed_forecasts,
    }
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SmartGrid forecast/anomaly benchmark matrix.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="Model-ready CSV input file")
    parser.add_argument("--group-by", default="source")
    parser.add_argument("--freq-minutes", type=int, default=30)
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--folds", type=int, default=20)
    parser.add_argument("--injected-file", default=None, help="Injected CSV with synthetic anomaly labels for sequence anomaly baselines")
    parser.add_argument("--lstm-window", type=int, default=48)
    parser.add_argument("--lstm-epochs", type=int, default=int(os.getenv("LSTM_AE_EPOCHS", "8")))
    parser.add_argument("--matrix-out", default=str(MATRIX_PATH))
    parser.add_argument("--comparison-out", default=str(COMPARISON_PATH))
    parser.add_argument("--forecast-metrics-out", default=str(FORECAST_METRICS_PATH))
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    injected_path = Path(args.injected_file) if args.injected_file else input_path.with_name(input_path.stem + "_injected.csv")
    if not injected_path.is_absolute():
        injected_path = ROOT / injected_path
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)

    experiments = []
    for spec in model_specs():
        reason = unavailable_reason(spec["required_modules"])
        if reason:
            experiments.append(
                {
                    "name": spec["name"],
                    "family": spec["family"],
                    "status": "unavailable",
                    "role": spec["role"],
                    "unavailable_reason": reason,
                    "required_modules": spec["required_modules"],
                }
            )
            continue
        if spec["runner"] is None:
            experiments.append(
                {
                    "name": spec["name"],
                    "family": spec["family"],
                    "status": "unavailable",
                    "role": spec["role"],
                    "unavailable_reason": "implementation requires optional dependency stack and is not part of the stdlib demo runner",
                    "required_modules": spec["required_modules"],
                }
            )
            continue
        if spec["runner"] == "lstm_autoencoder":
            if not injected_path.exists():
                experiments.append(
                    {
                        "name": spec["name"],
                        "family": spec["family"],
                        "status": "unavailable",
                        "role": spec["role"],
                        "unavailable_reason": f"injected anomaly file not found: {relative(injected_path)}",
                    }
                )
            else:
                experiments.append(run_lstm_autoencoder(input_path, injected_path, args.group_by, spec, args.lstm_window, args.lstm_epochs))
            continue
        experiments.append(run_forecast_model(input_path, args.group_by, args.horizon_hours, args.folds, spec))

    payload = {
        "input_file": relative(input_path),
        "group_by": args.group_by,
        "freq_minutes": args.freq_minutes,
        "horizon_hours": args.horizon_hours,
        "horizon_steps": max(1, int((args.horizon_hours * 60) / args.freq_minutes)),
        "folds": args.folds,
        "injected_file": relative(injected_path) if injected_path.exists() else None,
        "experiments": experiments,
    }

    matrix_out = Path(args.matrix_out)
    comparison_out = Path(args.comparison_out)
    forecast_metrics_out = Path(args.forecast_metrics_out)
    if not matrix_out.is_absolute():
        matrix_out = ROOT / matrix_out
    if not comparison_out.is_absolute():
        comparison_out = ROOT / comparison_out
    if not forecast_metrics_out.is_absolute():
        forecast_metrics_out = ROOT / forecast_metrics_out
    write_matrix(matrix_out, payload)
    write_comparison(comparison_out, payload)
    write_canonical_forecast_metrics(forecast_metrics_out, payload)
    print(f"[benchmark] wrote {matrix_out}")
    print(f"[benchmark] wrote {comparison_out}")
    print(f"[benchmark] wrote {forecast_metrics_out}")


if __name__ == "__main__":
    main()
