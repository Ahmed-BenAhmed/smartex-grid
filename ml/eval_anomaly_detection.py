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

from anomaly_detection import AnomalyConfig, detect_anomalies_in_file, rolling_median_mad_anomalies


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "model_ready" / "demo_meter_readings_60m_injected.csv"
REPORT_DIR = ROOT / "reports" / "ml"
EPSILON = 1e-9


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def bool_value(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def read_flags(path: Path, group_by: str) -> Dict[str, List[Tuple[datetime, bool, str]]]:
    groups: Dict[str, List[Tuple[datetime, bool, str]]] = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if group_by not in (reader.fieldnames or []):
            raise ValueError(f"group_by column '{group_by}' not found in {path}")
        for row in reader:
            anomaly_type = row.get("anomaly_type", "").strip()
            groups[row[group_by]].append((parse_time(row["time"]), bool_value(row.get("is_anomaly", "false")), anomaly_type))
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


def confusion_by_anomaly_type(truth: List[bool], pred: List[bool], anomaly_types: List[str]) -> dict:
    labels = sorted({part.strip() for value in anomaly_types for part in value.split("+") if part.strip()})
    return {
        label: confusion([truth_flag and label in value.split("+") for truth_flag, value in zip(truth, anomaly_types)], pred)
        for label in labels
    }


def anomaly_labels(anomaly_types: List[str]) -> List[str]:
    return sorted({part.strip() for value in anomaly_types for part in value.split("+") if part.strip()})


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


def max_consecutive_true(flags: List[bool]) -> int:
    best = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def min_flags_for_event(anomaly_type: str, default_min_flags: int) -> int:
    if anomaly_type.startswith("point_"):
        return 1
    return default_min_flags


def event_windows(truth: List[bool], anomaly_types: List[str]) -> List[dict]:
    events = []
    for start, end in contiguous_windows(truth):
        labels = anomaly_labels(anomaly_types[start : end + 1])
        events.append(
            {
                "start": start,
                "end": end,
                "type": "+".join(labels) if labels else "unknown",
            }
        )
    return events


def event_detection_metrics(
    truth: List[bool],
    pred: List[bool],
    anomaly_types: List[str],
    tolerance_steps: int,
    event_min_flags: int,
    event_min_consecutive: int,
) -> dict:
    events = event_windows(truth, anomaly_types)
    detected_events = []
    missed_events = []
    latencies = []
    covered_pred = [False] * len(pred)

    for event in events:
        search_start = max(0, event["start"] - tolerance_steps)
        search_end = min(len(pred) - 1, event["end"] + tolerance_steps)
        window_pred = pred[search_start : search_end + 1]
        required_flags = min_flags_for_event(event["type"], event_min_flags)
        enough_flags = sum(1 for flag in window_pred if flag) >= required_flags
        enough_consecutive = max_consecutive_true(window_pred) >= event_min_consecutive
        if enough_flags and enough_consecutive:
            detected_events.append(event)
            for idx in range(search_start, search_end + 1):
                if pred[idx]:
                    covered_pred[idx] = True
            first_detection = next((idx for idx in range(event["start"], search_end + 1) if pred[idx]), None)
            if first_detection is None:
                first_detection = next((idx for idx in range(search_start, search_end + 1) if pred[idx]), event["start"])
            latencies.append(max(0, first_detection - event["start"]))
        else:
            missed_events.append(event)

    false_positive_events = 0
    for start, end in contiguous_windows(pred):
        if any(covered_pred[start : end + 1]):
            continue
        if (end - start + 1) >= event_min_flags:
            false_positive_events += 1

    tp = len(detected_events)
    fp = false_positive_events
    fn = len(missed_events)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall) / max(precision + recall, EPSILON)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "events": len(events),
        "detected_events": tp,
        "missed_events": fn,
        "avg_latency_samples": sum(latencies) / len(latencies) if latencies else None,
    }


def event_metrics_by_type(
    truth: List[bool],
    pred: List[bool],
    anomaly_types: List[str],
    tolerance_steps: int,
    event_min_flags: int,
    event_min_consecutive: int,
) -> dict:
    payload = {}
    for label in anomaly_labels(anomaly_types):
        typed_truth = [truth_flag and label in value.split("+") for truth_flag, value in zip(truth, anomaly_types)]
        payload[label] = event_detection_metrics(
            typed_truth,
            pred,
            [label if flag else "" for flag in typed_truth],
            tolerance_steps,
            event_min_flags,
            event_min_consecutive,
        )
    return payload


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


def read_forecast_map(path: Path) -> Dict[Tuple[str, datetime], dict]:
    forecasts: Dict[Tuple[str, datetime], dict] = {}
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"group_key", "time", "forecast"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Forecast file {path} is missing columns: {sorted(missing)}")
        for row in reader:
            key = (row["group_key"], parse_time(row["time"]))
            horizon_step = int(row.get("horizon_step", "999999") or "999999")
            forecast = {
                "forecast": float(row["forecast"]),
                "model_type": row.get("model_type", "unknown"),
                "horizon_step": horizon_step,
            }
            existing = forecasts.get(key)
            if existing is None or horizon_step < existing["horizon_step"]:
                forecasts[key] = forecast
    return forecasts


def detect_forecast_residual_anomalies(
    input_path: Path,
    forecast_path: Path,
    group_by: str,
    cfg: AnomalyConfig,
) -> Tuple[Path, Path, Dict[str, List[Tuple[datetime, bool, bool]]]]:
    out_csv = input_path.with_name(input_path.stem + "_forecast_residual_anomalies.csv")
    report_json = input_path.with_name(input_path.stem + "_forecast_residual_anomalies_report.json")
    forecast_map = read_forecast_map(forecast_path)

    rows: List[dict] = []
    groups: Dict[str, List[Tuple[datetime, float, int, float | None]]] = defaultdict(list)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if group_by not in fieldnames:
            raise ValueError(f"group_by column '{group_by}' not found in {input_path}")
        if "forecast_yhat" not in fieldnames:
            fieldnames.append("forecast_yhat")
        if "forecast_residual" not in fieldnames:
            fieldnames.append("forecast_residual")
        if "is_anomaly" not in fieldnames:
            fieldnames.append("is_anomaly")
        for idx, row in enumerate(reader):
            rows.append(row)
            key = row[group_by]
            time_value = parse_time(row["time"])
            forecast = forecast_map.get((key, time_value))
            yhat = forecast["forecast"] if forecast else None
            groups[key].append((time_value, float(row["kwh"]), idx, yhat))

    prediction_groups: Dict[str, List[Tuple[datetime, bool, bool]]] = {}
    report = {
        "input_file": relative(input_path),
        "forecast_file": relative(forecast_path),
        "detector": "forecast_residual_mad",
        "groups": {},
    }
    predicted_flags = [False] * len(rows)

    for key, series in sorted(groups.items()):
        ordered = sorted(series, key=lambda item: item[0])
        covered = [(time_value, actual, idx, yhat) for time_value, actual, idx, yhat in ordered if yhat is not None]
        covered_flags: Dict[int, bool] = {}
        if covered:
            residuals = [actual - float(yhat) for _time_value, actual, _idx, yhat in covered]
            flags = rolling_median_mad_anomalies(residuals, cfg)
            covered_flags = {idx: flag for (_time_value, _actual, idx, _yhat), flag in zip(covered, flags)}
        detected = 0
        for time_value, actual, idx, yhat in ordered:
            is_covered = yhat is not None
            if is_covered:
                residual = actual - float(yhat)
                rows[idx]["forecast_yhat"] = f"{float(yhat):.8f}"
                rows[idx]["forecast_residual"] = f"{residual:.8f}"
            else:
                rows[idx]["forecast_yhat"] = ""
                rows[idx]["forecast_residual"] = ""
            flag = covered_flags.get(idx, False)
            predicted_flags[idx] = flag
            if flag:
                detected += 1
        prediction_groups[key] = [(time_value, predicted_flags[idx], yhat is not None) for time_value, _actual, idx, yhat in ordered]
        report["groups"][key] = {
            "samples": len(ordered),
            "forecast_covered_samples": len(covered),
            "detected": detected,
        }

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row, flag in zip(rows, predicted_flags):
            row_out = dict(row)
            row_out["is_anomaly"] = "true" if flag else "false"
            writer.writerow(row_out)

    with report_json.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    print(f"[forecast-residuals] {input_path.name} -> {out_csv.name} (groups: {len(report['groups'])})")
    return out_csv, report_json, prediction_groups


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
    forecast_file: Path | None = None,
    forecast_coverage_only: bool = True,
    event_min_flags: int = 5,
    event_min_consecutive: int = 1,
) -> dict:
    cfg = AnomalyConfig(window=window, mad_multiplier=mad_multiplier, min_abs_deviation=min_abs_deviation)
    if forecast_file is None:
        prediction_csv, detector_report = detect_anomalies_in_file(
            input_path,
            cfg,
            group_by=group_by,
            preserve_existing=False,
        )
        pred_groups_raw = read_flags(prediction_csv, group_by)
        pred_groups = {
            key: [(time_value, flag, True) for time_value, flag, _anomaly_type in values]
            for key, values in pred_groups_raw.items()
        }
        detector = "seasonal_residual_mad"
    else:
        prediction_csv, detector_report, pred_groups = detect_forecast_residual_anomalies(input_path, forecast_file, group_by, cfg)
        detector = "forecast_residual_mad"
    truth_groups = read_flags(input_path, group_by)

    all_truth: List[bool] = []
    all_pred: List[bool] = []
    all_types: List[str] = []
    group_payload = {}
    evaluated_rows = 0
    covered_rows = 0
    for key in sorted(truth_groups):
        truth_series = truth_groups[key]
        pred_series = pred_groups.get(key, [])
        if len(pred_series) != len(truth_series):
            raise ValueError(f"Prediction length mismatch for group {key}")
        aligned = [
            (truth_item[0], truth_item[1], truth_item[2], pred_item[1], pred_item[2])
            for truth_item, pred_item in zip(truth_series, pred_series)
            if not forecast_coverage_only or pred_item[2]
        ]
        covered_rows += sum(1 for item in pred_series if item[2])
        evaluated_rows += len(aligned)
        times = [item[0] for item in aligned]
        truth_flags = [item[1] for item in aligned]
        anomaly_types = [item[2] for item in aligned]
        pred_flags = [item[3] for item in aligned]
        all_truth.extend(truth_flags)
        all_pred.extend(pred_flags)
        all_types.extend(anomaly_types)
        group_payload[key] = {
            **confusion(truth_flags, pred_flags),
            **latency_stats(times, truth_flags, pred_flags, tolerance_steps),
            "by_anomaly_type": confusion_by_anomaly_type(truth_flags, pred_flags, anomaly_types),
            "event_level": event_detection_metrics(
                truth_flags,
                pred_flags,
                anomaly_types,
                tolerance_steps,
                event_min_flags,
                event_min_consecutive,
            ),
            "event_level_by_anomaly_type": event_metrics_by_type(
                truth_flags,
                pred_flags,
                anomaly_types,
                tolerance_steps,
                event_min_flags,
                event_min_consecutive,
            ),
            "evaluated_rows": len(aligned),
        }

    return {
        "input_file": relative(input_path),
        "prediction_file": relative(prediction_csv),
        "detector_report": relative(detector_report),
        "forecast_file": relative(forecast_file) if forecast_file else None,
        "detector": detector,
        "group_by": group_by,
        "window": window,
        "mad_multiplier": mad_multiplier,
        "min_abs_deviation": min_abs_deviation,
        "tolerance_steps": tolerance_steps,
        "forecast_coverage_only": bool(forecast_file and forecast_coverage_only),
        "evaluated_rows": evaluated_rows,
        "forecast_covered_rows": covered_rows,
        "overall": confusion(all_truth, all_pred),
        "by_anomaly_type": confusion_by_anomaly_type(all_truth, all_pred, all_types),
        "event_level": event_detection_metrics(
            all_truth,
            all_pred,
            all_types,
            tolerance_steps,
            event_min_flags,
            event_min_consecutive,
        ),
        "event_level_by_anomaly_type": event_metrics_by_type(
            all_truth,
            all_pred,
            all_types,
            tolerance_steps,
            event_min_flags,
            event_min_consecutive,
        ),
        "event_scoring": {
            "event_min_flags": event_min_flags,
            "event_min_consecutive": event_min_consecutive,
            "point_events_override_min_flags": 1,
        },
        "groups": group_payload,
    }


def write_markdown(path: Path, payload: dict) -> None:
    overall = payload["overall"]
    event_level = payload.get("event_level", {})
    lines = [
        "# ML Demo Summary",
        "",
        f"Input: `{payload['input_file']}`",
        f"Predictions: `{payload['prediction_file']}`",
        "",
        "## Anomaly Detection Metrics",
        "",
        f"- Detector: {payload.get('detector', 'unknown')}",
        f"- Precision: {overall['precision']:.4f}",
        f"- Recall: {overall['recall']:.4f}",
        f"- F1: {overall['f1']:.4f}",
        f"- TP/FP/FN/TN: {overall['tp']}/{overall['fp']}/{overall['fn']}/{overall['tn']}",
        f"- Event Precision: {event_level.get('precision', 0):.4f}",
        f"- Event Recall: {event_level.get('recall', 0):.4f}",
        f"- Event F1: {event_level.get('f1', 0):.4f}",
        f"- Evaluated rows: {payload.get('evaluated_rows', 0)}",
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
    parser.add_argument("--forecast-file", default=None, help="Forecast CSV used to compute actual - yhat residuals")
    parser.add_argument("--event-min-flags", type=int, default=5, help="Minimum flags inside a non-point anomaly window for event-level detection")
    parser.add_argument("--event-min-consecutive", type=int, default=1, help="Minimum consecutive flags inside an anomaly window for event-level detection")
    parser.add_argument(
        "--all-input-rows",
        action="store_true",
        help="When --forecast-file is set, score rows without a forecast as detector negatives instead of limiting to forecast-covered rows.",
    )
    parser.add_argument("--metrics-out", default=str(REPORT_DIR / "anomaly_eval_metrics.json"))
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / args.input
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    forecast_file = Path(args.forecast_file) if args.forecast_file else None
    if forecast_file is not None and not forecast_file.is_absolute():
        forecast_file = ROOT / forecast_file
    payload = evaluate(
        input_path,
        args.group_by,
        args.window,
        args.mad_multiplier,
        args.min_abs_deviation,
        args.tolerance_steps,
        forecast_file=forecast_file,
        forecast_coverage_only=not args.all_input_rows,
        event_min_flags=args.event_min_flags,
        event_min_consecutive=args.event_min_consecutive,
    )

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
