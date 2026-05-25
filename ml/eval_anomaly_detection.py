"""Evaluate anomaly detection on injected smart-meter CSVs.

The input CSV should contain ground-truth labels in `is_anomaly`, typically
created by `ml/inject_anomalies.py`. This script runs the offline MAD detector,
compares predicted labels against ground truth, and writes reports under
reports/ml/.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Dict, List, Tuple

from anomaly_detection import AnomalyConfig, detect_anomalies_in_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "model_ready" / "demo_meter_readings_60m_injected.csv"
REPORT_DIR = ROOT / "reports" / "ml"
EPSILON = 1e-9


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def bool_value(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def read_flags(path: Path, group_by: str) -> Dict[str, List[Tuple[datetime, bool]]]:
    groups: Dict[str, List[Tuple[datetime, bool]]] = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if group_by not in (reader.fieldnames or []):
            raise ValueError(f"group_by column '{group_by}' not found in {path}")
        for row in reader:
            groups[row[group_by]].append((parse_time(row["time"]), bool_value(row.get("is_anomaly", "false"))))
    return {key: sorted(values, key=lambda item: item[0]) for key, values in groups.items()}


def confusion(truth: List[bool], pred: List[bool]) -> dict:
    tp = sum(1 for t, p in zip(truth, pred) if t and p)
    fp = sum(1 for t, p in zip(truth, pred) if not t and p)
    fn = sum(1 for t, p in zip(truth, pred) if t and not p)
    tn = sum(1 for t, p in zip(truth, pred) if not t and not p)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall) / max(precision + recall, EPSILON)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1}


def contiguous_windows(flags: List[bool]) -> List[Tuple[int, int]]:
    windows: List[Tuple[int, int]] = []
    start = None
    for idx, flag in enumerate(flags):
        if flag and start is None:
            start = idx
        elif not flag and start is not None:
            windows.append((start, idx - 1))
            start = None
    if start is not None:
        windows.append((start, len(flags) - 1))
    return windows


def infer_cadence_minutes(times: List[datetime]) -> int | None:
    deltas = []
    for prev, cur in zip(times, times[1:]):
        minutes = int((cur - prev).total_seconds() // 60)
        if minutes > 0:
            deltas.append(minutes)
    return int(median(deltas)) if deltas else None


def latency_stats(times: List[datetime], truth: List[bool], pred: List[bool], tolerance_steps: int) -> dict:
    latencies = []
    missed = 0
    for start, end in contiguous_windows(truth):
        search_end = min(len(pred) - 1, end + tolerance_steps)
        detected_at = None
        for idx in range(start, search_end + 1):
            if pred[idx]:
                detected_at = idx
                break
        if detected_at is None:
            missed += 1
        else:
            latencies.append(max(0, detected_at - start))
    cadence = infer_cadence_minutes(times)
    avg_samples = sum(latencies) / len(latencies) if latencies else None
    avg_minutes = avg_samples * cadence if avg_samples is not None and cadence is not None else None
    return {
        "windows": len(contiguous_windows(truth)),
        "missed_windows": missed,
        "avg_latency_samples": avg_samples,
        "avg_latency_minutes": avg_minutes,
    }


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def evaluate(
    input_path: Path,
    group_by: str,
    window: int,
    mad_multiplier: float,
    min_abs_deviation: float,
    tolerance_steps: int,
) -> dict:
    prediction_csv, detector_report = detect_anomalies_in_file(
        input_path,
        AnomalyConfig(window=window, mad_multiplier=mad_multiplier, min_abs_deviation=min_abs_deviation),
        group_by=group_by,
        preserve_existing=False,
    )
    truth_groups = read_flags(input_path, group_by)
    pred_groups = read_flags(prediction_csv, group_by)

    all_truth: List[bool] = []
    all_pred: List[bool] = []
    group_payload = {}
    for key in sorted(truth_groups):
        truth_series = truth_groups[key]
        pred_series = pred_groups.get(key, [])
        times = [item[0] for item in truth_series]
        truth_flags = [item[1] for item in truth_series]
        pred_flags = [item[1] for item in pred_series]
        if len(pred_flags) != len(truth_flags):
            raise ValueError(f"Prediction length mismatch for group {key}")
        all_truth.extend(truth_flags)
        all_pred.extend(pred_flags)
        group_payload[key] = {
            **confusion(truth_flags, pred_flags),
            **latency_stats(times, truth_flags, pred_flags, tolerance_steps),
        }

    return {
        "input_file": relative(input_path),
        "prediction_file": relative(prediction_csv),
        "detector_report": relative(detector_report),
        "group_by": group_by,
        "window": window,
        "mad_multiplier": mad_multiplier,
        "min_abs_deviation": min_abs_deviation,
        "tolerance_steps": tolerance_steps,
        "overall": confusion(all_truth, all_pred),
        "groups": group_payload,
    }


def write_markdown(path: Path, payload: dict) -> None:
    overall = payload["overall"]
    lines = [
        "# ML Demo Summary",
        "",
        f"Input: `{payload['input_file']}`",
        f"Predictions: `{payload['prediction_file']}`",
        "",
        "## Anomaly Detection Metrics",
        "",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- TP/FP/FN/TN: {overall['tp']}/{overall['fp']}/{overall['fn']}/{overall['tn']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate offline anomaly detection against injected labels.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="Injected model-ready CSV")
    parser.add_argument("--group-by", default="meter_id")
    parser.add_argument("--window", type=int, default=24)
    parser.add_argument("--mad-multiplier", type=float, default=3.5)
    parser.add_argument("--min-abs-deviation", type=float, default=0.12)
    parser.add_argument("--tolerance-steps", type=int, default=2)
    parser.add_argument("--metrics-out", default=str(REPORT_DIR / "anomaly_eval_metrics.json"))
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / args.input
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = evaluate(input_path, args.group_by, args.window, args.mad_multiplier, args.min_abs_deviation, args.tolerance_steps)

    metrics_path = Path(args.metrics_out)
    if not metrics_path.is_absolute():
        metrics_path = ROOT / metrics_path
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(REPORT_DIR / "ml_demo_summary.md", payload)
    print(f"[eval] wrote {metrics_path}")
    print(f"[eval] wrote {REPORT_DIR / 'ml_demo_summary.md'}")


if __name__ == "__main__":
    main()
