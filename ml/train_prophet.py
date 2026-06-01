"""CSV-first forecasting evaluation for smart-grid meter data.

The script is intentionally usable without Prophet. It tries Prophet only when
requested/available and otherwise uses a deterministic seasonal-naive fallback.

Outputs:
- reports/ml/forecast_metrics.json
- reports/ml/forecasts/<input_stem>_forecasts.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "model_ready" / "demo_meter_readings_60m.csv"
REPORT_DIR = ROOT / "reports" / "ml"
FORECAST_DIR = REPORT_DIR / "forecasts"
EPSILON = 1e-9


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def wape(actual: Sequence[float], forecast: Sequence[float]) -> float:
    denominator = max(sum(abs(v) for v in actual), EPSILON)
    return sum(abs(a - f) for a, f in zip(actual, forecast)) / denominator


def read_grouped_csv(path: Path, group_by: str) -> Dict[str, List[Tuple[datetime, float]]]:
    groups: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if group_by not in (reader.fieldnames or []):
            raise ValueError(f"group_by column '{group_by}' not found in {path}")
        for row in reader:
            groups[row[group_by]].append((parse_time(row["time"]), float(row["kwh"])))
    return {key: sorted(values, key=lambda item: item[0]) for key, values in groups.items()}


def infer_cadence_minutes(times: Sequence[datetime]) -> int:
    deltas = []
    for prev, cur in zip(times, times[1:]):
        minutes = int((cur - prev).total_seconds() // 60)
        if minutes > 0:
            deltas.append(minutes)
    return int(median(deltas)) if deltas else 60


def horizon_steps(horizon_hours: int, cadence_minutes: int) -> int:
    return max(1, int((horizon_hours * 60) / cadence_minutes))


def choose_cutoffs(n: int, start: int, horizon: int, folds: int) -> List[int]:
    end = n - horizon
    if end <= start:
        return []
    if folds <= 1:
        return [end]
    step = max(1, (end - start) // (folds - 1))
    cutoffs = [start + i * step for i in range(folds)]
    return sorted({min(c, end) for c in cutoffs if c <= end})


def seasonal_naive_forecast(values: Sequence[float], cutoff: int, horizon: int, season_steps: int) -> List[float]:
    result: List[float] = []
    fallback = values[cutoff - 1]
    for offset in range(horizon):
        target_idx = cutoff + offset
        reference_idx = target_idx - season_steps
        result.append(values[reference_idx] if reference_idx >= 0 else fallback)
    return result


def prophet_forecast(
    times: Sequence[datetime],
    values: Sequence[float],
    cutoff: int,
    horizon: int,
    cadence_minutes: int,
    prophet_params: dict | None = None,
) -> List[float]:
    try:
        import pandas as pd
        from prophet import Prophet
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"Prophet unavailable: {exc}") from exc

    train_df = pd.DataFrame({"ds": list(times[:cutoff]), "y": list(values[:cutoff])})
    params = {
        "daily_seasonality": True,
        "weekly_seasonality": True,
        "yearly_seasonality": False,
    }
    if prophet_params:
        params.update(prophet_params)
    model = Prophet(**params)
    model.fit(train_df)
    future = model.make_future_dataframe(periods=horizon, freq=f"{cadence_minutes}min", include_history=False)
    forecast = model.predict(future)
    return [float(v) for v in forecast["yhat"].tolist()[:horizon]]


def evaluate_group(
    group_key: str,
    series: Sequence[Tuple[datetime, float]],
    model: str,
    horizon_hours_value: int,
    folds: int,
) -> Tuple[List[dict], dict]:
    times = [item[0] for item in series]
    values = [item[1] for item in series]
    cadence = infer_cadence_minutes(times)
    horizon = horizon_steps(horizon_hours_value, cadence)
    season_steps = horizon_steps(24, cadence)
    start = max(season_steps, horizon)
    cutoffs = choose_cutoffs(len(values), start=start, horizon=horizon, folds=folds)

    forecast_rows: List[dict] = []
    one_step_actual: List[float] = []
    one_step_forecast: List[float] = []
    horizon_actual: List[float] = []
    horizon_forecast: List[float] = []
    model_used = model

    for fold_idx, cutoff in enumerate(cutoffs, start=1):
        if model in {"prophet", "prophet_tuned", "auto"}:
            try:
                prophet_params = None
                if model == "prophet_tuned":
                    prophet_params = {
                        "changepoint_prior_scale": 0.03,
                        "seasonality_prior_scale": 5.0,
                        "seasonality_mode": "additive",
                    }
                preds = prophet_forecast(times, values, cutoff, horizon, cadence, prophet_params=prophet_params)
                model_used = "prophet_tuned" if model == "prophet_tuned" else "prophet"
            except Exception:
                preds = seasonal_naive_forecast(values, cutoff, horizon, season_steps)
                model_used = "seasonal_naive_fallback"
        else:
            preds = seasonal_naive_forecast(values, cutoff, horizon, season_steps)
            model_used = "seasonal_naive_fallback"

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
                    "model_type": model_used,
                }
            )
        if actuals and preds:
            one_step_actual.append(actuals[0])
            one_step_forecast.append(preds[0])
            horizon_actual.extend(actuals)
            horizon_forecast.extend(preds)

    metrics = {
        "group_key": group_key,
        "samples": len(values),
        "cadence_minutes": cadence,
        "horizon_hours": horizon_hours_value,
        "horizon_steps": horizon,
        "folds_requested": folds,
        "folds_used": len(cutoffs),
        "model_type": model_used,
        "wape_1_step": wape(one_step_actual, one_step_forecast) if one_step_actual else math.nan,
        "wape_horizon": wape(horizon_actual, horizon_forecast) if horizon_actual else math.nan,
    }
    return forecast_rows, metrics


def write_forecasts(path: Path, rows: Iterable[dict]) -> None:
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["group_key", "fold", "horizon_step", "time", "actual", "forecast", "model_type"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_metrics(path: Path, payload: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CSV-first Prophet/seasonal-naive forecasts.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="Model-ready CSV input file")
    parser.add_argument("--group-by", default="meter_id", help="Natural group column (default: meter_id)")
    parser.add_argument("--horizon-hours", type=int, default=24, help="Forecast horizon in hours")
    parser.add_argument("--folds", type=int, default=5, help="Rolling-origin folds")
    parser.add_argument("--model", choices=["auto", "prophet", "prophet_tuned", "seasonal_naive"], default="auto")
    parser.add_argument("--metrics-out", default=str(REPORT_DIR / "forecast_metrics.json"))
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / args.input
    groups = read_grouped_csv(input_path, args.group_by)

    all_forecasts: List[dict] = []
    group_metrics: List[dict] = []
    for group_key, series in sorted(groups.items()):
        forecasts, metrics = evaluate_group(group_key, series, args.model, args.horizon_hours, args.folds)
        all_forecasts.extend(forecasts)
        group_metrics.append(metrics)

    one_actual = [float(row["actual"]) for row in all_forecasts if int(row["horizon_step"]) == 1]
    one_forecast = [float(row["forecast"]) for row in all_forecasts if int(row["horizon_step"]) == 1]
    all_actual = [float(row["actual"]) for row in all_forecasts]
    all_pred = [float(row["forecast"]) for row in all_forecasts]
    payload = {
        "input_file": relative(input_path),
        "group_by": args.group_by,
        "model_requested": args.model,
        "horizon_hours": args.horizon_hours,
        "groups": group_metrics,
        "overall": {
            "groups": len(group_metrics),
            "forecast_rows": len(all_forecasts),
            "wape_1_step": wape(one_actual, one_forecast) if one_actual else math.nan,
            "wape_horizon": wape(all_actual, all_pred) if all_actual else math.nan,
        },
    }

    forecast_path = FORECAST_DIR / f"{input_path.stem}_forecasts.csv"
    write_forecasts(forecast_path, all_forecasts)
    write_metrics(Path(args.metrics_out), payload)
    print(f"[forecast] wrote {forecast_path}")
    print(f"[forecast] wrote {args.metrics_out}")


if __name__ == "__main__":
    main()
