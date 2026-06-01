"""Inject synthetic anomaly ground truth into canonical smart-meter CSVs.

Supported perturbations:
- point spikes/drops
- contextual segment swaps
- trend drift

The output preserves the input schema and sets `is_anomaly=true` on injected
ground-truth timestamps.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "model_ready" / "demo_meter_readings_60m.csv"


def bool_value(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def read_rows(path: Path) -> Tuple[List[dict], List[str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        fieldnames = list(reader.fieldnames or [])
    if "is_anomaly" not in fieldnames:
        fieldnames.append("is_anomaly")
        for row in rows:
            row["is_anomaly"] = "false"
    if "anomaly_type" not in fieldnames:
        fieldnames.append("anomaly_type")
        for row in rows:
            row["anomaly_type"] = ""
    return rows, fieldnames


def write_rows(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def group_indices(rows: List[dict], group_by: str) -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        groups[row[group_by]].append(idx)
    return groups


def series_std(rows: List[dict], indices: List[int]) -> float:
    values = [float(rows[idx]["kwh"]) for idx in indices]
    return pstdev(values) if len(values) > 1 else 0.0


def mark(row: dict, anomaly_type: str) -> None:
    row["is_anomaly"] = "true"
    existing = row.get("anomaly_type", "").strip()
    if not existing:
        row["anomaly_type"] = anomaly_type
    elif anomaly_type not in {part.strip() for part in existing.split("+")}:
        row["anomaly_type"] = f"{existing}+{anomaly_type}"


def inject_point(rows: List[dict], indices: List[int], rng: random.Random, report: list, spike_k: float, drop_factor: float) -> None:
    if len(indices) < 8:
        return
    std = max(series_std(rows, indices), 0.01)
    local_idx = rng.randrange(len(indices) * 3 // 4, max(len(indices) * 3 // 4 + 1, len(indices) - 1))
    row_idx = indices[local_idx]
    original = float(rows[row_idx]["kwh"])
    if rng.random() < 0.5:
        rows[row_idx]["kwh"] = f"{max(0.0, original - drop_factor * original):.8f}"
        kind = "point_drop"
    else:
        rows[row_idx]["kwh"] = f"{original + spike_k * std:.8f}"
        kind = "point_spike"
    mark(rows[row_idx], kind)
    report.append({"type": kind, "start_index": row_idx, "end_index": row_idx, "time": rows[row_idx]["time"]})


def inject_contextual_swap(rows: List[dict], indices: List[int], rng: random.Random, report: list, segment_steps: int) -> None:
    """Swap normal night and afternoon segments.

    This creates contextual anomalies: each swapped value can be globally
    plausible, but it is wrong for its time-of-day context.
    """
    if len(indices) < segment_steps * 3:
        return
    by_time = {parse_time(rows[idx]["time"]): idx for idx in indices}
    days = sorted({parse_time(rows[idx]["time"]).date() for idx in indices})
    candidate_segments = []
    sorted_times = sorted(by_time)
    cadence = None
    for prev, cur in zip(sorted_times, sorted_times[1:]):
        delta = int((cur - prev).total_seconds() // 60)
        if delta > 0:
            cadence = delta
            break
    cadence = cadence or 30
    for day in days[len(days) // 2 :]:
        night_start = datetime.combine(day, datetime.min.time()).replace(hour=2)
        day_start = datetime.combine(day, datetime.min.time()).replace(hour=14)
        night = []
        afternoon = []
        for step in range(segment_steps):
            night_time = night_start + timedelta(minutes=cadence * step)
            day_time = day_start + timedelta(minutes=cadence * step)
            if night_time in by_time and day_time in by_time:
                night.append(by_time[night_time])
                afternoon.append(by_time[day_time])
        if len(night) == segment_steps and len(afternoon) == segment_steps:
            candidate_segments.append((night, afternoon))
    if not candidate_segments:
        return
    # Keep the deterministic demo anomalies inside the final validation horizon.
    # Earlier candidates are useful for ad-hoc experiments, but the benchmark
    # report scores forecast-covered rows only.
    first, second = candidate_segments[-1]
    first_values = [rows[idx]["kwh"] for idx in first]
    second_values = [rows[idx]["kwh"] for idx in second]
    for idx, value in zip(first, second_values):
        rows[idx]["kwh"] = value
        mark(rows[idx], "contextual_day_night_swap")
    for idx, value in zip(second, first_values):
        rows[idx]["kwh"] = value
        mark(rows[idx], "contextual_day_night_swap")
    report.append(
        {
            "type": "contextual_day_night_swap",
            "night_start_index": first[0],
            "night_end_index": first[-1],
            "afternoon_start_index": second[0],
            "afternoon_end_index": second[-1],
            "night_start_time": rows[first[0]]["time"],
            "afternoon_start_time": rows[second[0]]["time"],
            "segment_steps": segment_steps,
        }
    )


def inject_trend_drift(rows: List[dict], indices: List[int], rng: random.Random, report: list, drift_steps: int, drift_percent: float) -> None:
    if len(indices) < drift_steps * 2:
        return
    # Put the drift near the end of the series so rolling-origin forecast
    # artifacts contain the full degradation window.
    start_local = max(0, len(indices) - drift_steps)
    drift_indices = indices[start_local : start_local + drift_steps]
    baseline = mean(float(rows[idx]["kwh"]) for idx in indices)
    max_delta = baseline * drift_percent
    for step, idx in enumerate(drift_indices, start=1):
        original = float(rows[idx]["kwh"])
        rows[idx]["kwh"] = f"{original + max_delta * (step / drift_steps):.8f}"
        mark(rows[idx], "trend_drift")
    report.append(
        {
            "type": "trend_drift",
            "start_index": drift_indices[0],
            "end_index": drift_indices[-1],
            "steps": drift_steps,
            "drift_percent": drift_percent,
        }
    )


def inject_anomalies(
    rows: List[dict],
    group_by: str,
    seed: int,
    point_per_group: int,
    segment_steps: int,
    drift_steps: int,
    spike_k: float,
    drift_percent: float,
) -> dict:
    rng = random.Random(seed)
    groups = group_indices(rows, group_by)
    report = {"seed": seed, "group_by": group_by, "groups": {}}

    for group_key, indices in sorted(groups.items()):
        indices = sorted(indices, key=lambda idx: rows[idx]["time"])
        group_report: List[dict] = []
        for _ in range(point_per_group):
            inject_point(rows, indices, rng, group_report, spike_k=spike_k, drop_factor=0.85)
        inject_contextual_swap(rows, indices, rng, group_report, segment_steps=segment_steps)
        inject_trend_drift(rows, indices, rng, group_report, drift_steps=drift_steps, drift_percent=drift_percent)
        report["groups"][group_key] = group_report
    report["total_ground_truth_rows"] = sum(1 for row in rows if bool_value(row.get("is_anomaly", "false")))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject synthetic anomaly ground truth into model-ready CSVs.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="Input model-ready CSV")
    parser.add_argument("--out", help="Output injected CSV path")
    parser.add_argument("--group-by", default="meter_id")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--point-per-group", type=int, default=5)
    parser.add_argument("--segment-steps", type=int, default=6)
    parser.add_argument("--drift-steps", type=int, default=6)
    parser.add_argument("--spike-k", type=float, default=10.0)
    parser.add_argument("--drift-percent", type=float, default=0.50)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / args.input
    output_path = Path(args.out) if args.out else input_path.with_name(input_path.stem + "_injected.csv")
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    rows, fieldnames = read_rows(input_path)
    if args.group_by not in fieldnames:
        raise ValueError(f"group_by column '{args.group_by}' not found in {input_path}")

    for row in rows:
        row["is_anomaly"] = "true" if bool_value(row.get("is_anomaly", "false")) else "false"
        if not bool_value(row["is_anomaly"]):
            row["anomaly_type"] = ""
    report = inject_anomalies(
        rows,
        group_by=args.group_by,
        seed=args.seed,
        point_per_group=args.point_per_group,
        segment_steps=args.segment_steps,
        drift_steps=args.drift_steps,
        spike_k=args.spike_k,
        drift_percent=args.drift_percent,
    )
    write_rows(output_path, rows, fieldnames)
    report_path = output_path.with_name(output_path.stem + "_injection_report.json")
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(f"[inject] wrote {output_path}")
    print(f"[inject] wrote {report_path}")


if __name__ == "__main__":
    main()
