"""
Anomaly detection for smart-meter time series.

This module implements a lightweight pipeline that:

1. Reads model-ready CSVs (same schema: time,meter_id,kwh,is_anomaly,source).
2. Groups series by a natural metadata key (city/zone/disco/feeder/meter_id).
3. Runs two complementary detectors:
   - Rolling robust statistics on the series or residuals (median + MAD -> robust z-score)
   - Optional IsolationForest for point anomalies when a group has enough samples

Output:
 - A CSV alongside the input with `_anomalies.csv` suffix that sets `is_anomaly` to true
 - A JSON report summarizing detected anomalies per group

Design choices:
 - Clustering is intentionally not part of this pipeline. Natural metadata grouping
   should be used (see project plan).
 - The IsolationForest is optional and only runs when the group has >= 100 samples (configurable).

Usage:
    python -m smartex_grid.ml.anomaly_detection <file.csv>

"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Dict, List, Tuple

try:
    from sklearn.ensemble import IsolationForest
except Exception:
    IsolationForest = None  # optional


ROOT = Path(__file__).resolve().parents[1]
MODEL_READY_DIR = ROOT / "data" / "model_ready"


@dataclass
class AnomalyConfig:
    window: int = 24  # rolling window in samples (e.g., 24 hours)
    mad_multiplier: float = 3.5  # threshold multiplier for robust z-score
    min_abs_deviation: float = 0.0  # guardrail against tiny deviations with tiny MAD
    min_samples_iforest: int = 100  # min samples per group to run IsolationForest
    iforest_contamination: float = 0.01  # contamination param for IsolationForest


def parse_timestamp(value: str) -> datetime:
    # Simple ISO-like parser used for grouping; reuse logic from resample script if needed
    value = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def infer_cadence_minutes(times: List[datetime]) -> int:
    deltas = []
    for prev, cur in zip(times, times[1:]):
        minutes = int((cur - prev).total_seconds() // 60)
        if minutes > 0:
            deltas.append(minutes)
    return int(median(deltas)) if deltas else 60


def rolling_median_mad_anomalies(values: List[float], cfg: AnomalyConfig) -> List[bool]:
    """Return list of booleans marking anomalies based on rolling median+MAD robust z-score.

    The implementation returns False for the first `window` samples (not enough history).
    """
    arr = [float(v) for v in values]
    n = len(arr)
    is_anom = [False] * n
    w = cfg.window

    for i in range(w, n):
        window_vals = arr[i - w : i]
        med = median(window_vals)
        mad = median([abs(v - med) for v in window_vals])
        # Prevent division by zero
        denom = mad if mad > 0 else 1e-9
        deviation = abs(arr[i] - med)
        robust_z = deviation / denom
        if robust_z > cfg.mad_multiplier and deviation >= cfg.min_abs_deviation:
            is_anom[i] = True

    return is_anom


def seasonal_residual_anomalies(times: List[datetime], values: List[float], cfg: AnomalyConfig) -> List[bool]:
    """Detect contextual anomalies using residuals vs same historical time slot.

    Prefer the same slot from the previous week when enough data exists; this
    avoids flagging normal weekday/weekend level differences as anomalies.
    """
    if len(values) < cfg.window * 2:
        return [False] * len(values)
    cadence = infer_cadence_minutes(times)
    daily_steps = max(1, int((24 * 60) / cadence))
    weekly_steps = daily_steps * 7
    season_steps = weekly_steps if len(values) >= weekly_steps + cfg.window else daily_steps
    residuals = [0.0] * len(values)
    for idx in range(season_steps, len(values)):
        residuals[idx] = float(values[idx]) - float(values[idx - season_steps])
    flags = rolling_median_mad_anomalies(residuals, cfg)
    return [idx >= season_steps and flag for idx, flag in enumerate(flags)]


def isolation_forest_anomalies(values: List[float], cfg: AnomalyConfig) -> List[bool]:
    if IsolationForest is None:
        return [False] * len(values)

    if len(values) < cfg.min_samples_iforest:
        return [False] * len(values)

    try:
        import numpy as np
    except Exception:
        return [False] * len(values)

    model = IsolationForest(contamination=cfg.iforest_contamination, random_state=42)
    X = np.array(values).reshape(-1, 1)
    preds = model.fit_predict(X)
    # IsolationForest returns -1 for anomalies
    return [p == -1 for p in preds.tolist()]


def detect_anomalies_in_file(
    path: Path,
    cfg: AnomalyConfig,
    group_by: str = "meter_id",
    preserve_existing: bool = False,
) -> Tuple[Path, Path]:
    """Detect anomalies in a model-ready CSV.

    group_by: column name to group by; defaults to 'meter_id'. Other natural groups
    (city, zone, feeder_id, disco) are supported if present in CSV.
    """
    out_csv = path.with_name(path.stem + "_anomalies.csv")
    report_json = path.with_name(path.stem + "_anomalies_report.json")

    # Read rows grouped by (group_key -> list of (time, kwh, row_idx))
    rows: List[Dict[str, str]] = []
    groups: Dict[str, List[Tuple[str, float, int]]] = defaultdict(list)

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if group_by not in reader.fieldnames:
            raise ValueError(f"group_by '{group_by}' not in CSV columns: {reader.fieldnames}")

        for idx, row in enumerate(reader):
            rows.append(row)
            kwh = float(row.get("kwh", 0.0))
            key = row.get(group_by) or row.get("meter_id")
            groups[key].append((row["time"], kwh, idx))

    if preserve_existing:
        is_anomaly_flags = [row.get("is_anomaly", "false").strip().lower() in ("1", "true", "yes") for row in rows]
    else:
        is_anomaly_flags = [False] * len(rows)

    report: Dict[str, Dict[str, int]] = {}

    for key, series in groups.items():
        # Sort by time to ensure temporal order
        series_sorted = sorted(series, key=lambda x: x[0])
        time_strings, values, indices = zip(*series_sorted)
        times = [parse_timestamp(value) for value in time_strings]

        # Seasonal residual detector catches consumption anomalies without
        # treating normal daily peaks as anomalous raw values.
        seasonal_flags = seasonal_residual_anomalies(times, list(values), cfg)

        # Optional IsolationForest
        iforest_flags = isolation_forest_anomalies(list(values), cfg)

        combined = [s or i for s, i in zip(seasonal_flags, iforest_flags)]

        # Apply to global flags
        detected = 0
        for _t, flag, idx in zip(times, combined, indices):
            if flag and not is_anomaly_flags[idx]:
                is_anomaly_flags[idx] = True
            if flag:
                detected += 1

        report[key] = {"samples": len(values), "detected": detected}

    # Write output CSV with updated is_anomaly column
    fieldnames = list(rows[0].keys()) if rows else ["time", "meter_id", "kwh", "is_anomaly", "source"]
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row, flag in zip(rows, is_anomaly_flags):
            row_out = dict(row)
            row_out["is_anomaly"] = "true" if flag else "false"
            writer.writerow(row_out)

    with report_json.open("w", encoding="utf-8") as handle:
        json.dump({"file": str(path), "groups": report}, handle, indent=2, ensure_ascii=False)

    print(f"[anomalies] {path.name} -> {out_csv.name} (groups: {len(report)})")
    return out_csv, report_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect anomalies in model-ready smart-meter CSVs.")
    parser.add_argument("files", nargs="*", help="CSV files to analyze. Defaults to all *_m.csv files in data/model_ready.")
    parser.add_argument("--group-by", type=str, default="meter_id", help="Column name to group by (city/zone/disco/feeder_id/meter_id)")
    parser.add_argument("--window", type=int, default=24, help="Rolling window size in samples for robust stats")
    parser.add_argument("--mad-multiplier", type=float, default=3.5, help="Robust MAD threshold multiplier")
    parser.add_argument("--min-abs-deviation", type=float, default=0.0, help="Minimum absolute deviation required for MAD flags")
    parser.add_argument("--preserve-existing", action="store_true", help="Keep existing is_anomaly=true labels in output")
    args = parser.parse_args()

    cfg = AnomalyConfig(window=args.window, mad_multiplier=args.mad_multiplier, min_abs_deviation=args.min_abs_deviation)

    if args.files:
        files = [Path(f) if Path(f).is_absolute() else ROOT / f for f in args.files]
    else:
        files = sorted(MODEL_READY_DIR.glob("*_m.csv")) + sorted(MODEL_READY_DIR.glob("*.csv"))

    if not files:
        raise FileNotFoundError(f"No model-ready CSV files found in {MODEL_READY_DIR}")

    for path in files:
        try:
            detect_anomalies_in_file(path, cfg, group_by=args.group_by, preserve_existing=args.preserve_existing)
        except Exception as exc:
            print(f"[error] {path}: {exc}")


if __name__ == "__main__":
    main()
