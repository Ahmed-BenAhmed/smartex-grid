"""Aggregate anomaly-detection evaluations across benchmark detectors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval_anomaly_detection import REPORT_DIR, evaluate, write_markdown


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_anomaly_thresholds import best_operating_point, default_thresholds  # noqa: E402


DEFAULT_INJECTED = ROOT / "data" / "model_ready" / "demo_meter_readings_30m_injected.csv"
DEFAULT_MATRIX = REPORT_DIR / "experiment_matrix.json"


def resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def residual_detector_name(model_name: str) -> str:
    return f"forecast_residual_mad__{model_name}"


def evaluate_residual_detector(
    input_path: Path,
    group_by: str,
    forecast_file: Path,
    model_name: str,
    window: int,
    event_min_flags: int,
    event_min_consecutive: int,
) -> dict:
    rows = [
        evaluate(
            input_path,
            group_by,
            window,
            threshold,
            min_abs_deviation=0.12,
            tolerance_steps=2,
            forecast_file=forecast_file,
            forecast_coverage_only=True,
            event_min_flags=event_min_flags,
            event_min_consecutive=event_min_consecutive,
        )
        for threshold in default_thresholds()
    ]
    best = best_operating_point(rows, min_precision=0.60)
    best["name"] = residual_detector_name(model_name)
    best["forecast_model"] = model_name
    best["family"] = "forecast_residual"
    best["status"] = "completed"
    best["threshold_sweep"] = [
        {
            "mad_multiplier": row["mad_multiplier"],
            "overall": row["overall"],
        }
        for row in rows
    ]
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate anomaly detectors across forecast and sequence baselines.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INJECTED))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--group-by", default="source")
    parser.add_argument("--window", type=int, default=24)
    parser.add_argument("--event-min-flags", type=int, default=5)
    parser.add_argument("--event-min-consecutive", type=int, default=1)
    parser.add_argument("--metrics-out", default=str(REPORT_DIR / "anomaly_eval_metrics.json"))
    args = parser.parse_args()

    input_path = resolve(args.input)
    matrix_path = resolve(args.matrix)
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))

    detectors = []
    for experiment in matrix.get("experiments", []):
        if experiment.get("family") != "forecast" or experiment.get("status") != "completed":
            continue
        forecast_file = experiment.get("forecast_file")
        if not forecast_file:
            continue
        detectors.append(
            evaluate_residual_detector(
                input_path,
                args.group_by,
                resolve(forecast_file),
                experiment["name"],
                args.window,
                args.event_min_flags,
                args.event_min_consecutive,
            )
        )

    lstm_metrics = REPORT_DIR / "lstm_autoencoder_eval_metrics.json"
    if lstm_metrics.exists():
        payload = json.loads(lstm_metrics.read_text(encoding="utf-8"))
        payload["name"] = "lstm_autoencoder"
        detectors.append(payload)

    if not detectors:
        raise RuntimeError("No anomaly detectors were evaluated.")

    best = max(detectors, key=lambda item: (item["overall"]["f1"], item["overall"]["recall"], item["overall"]["precision"]))
    best_event = max(
        detectors,
        key=lambda item: (
            item.get("event_level", {}).get("f1", 0),
            item.get("event_level", {}).get("recall", 0),
            item.get("event_level", {}).get("precision", 0),
        ),
    )
    payload = {
        "input_file": str(input_path.relative_to(ROOT)),
        "group_by": args.group_by,
        "selection_rule": "row-level best = max F1, then recall, then precision; event-level best = same rule on operational events",
        "best_detector": best["name"],
        "best_overall": best["overall"],
        "best_event_detector": best_event["name"],
        "best_event_overall": best_event.get("event_level", {}),
        "event_scoring": {
            "event_min_flags": args.event_min_flags,
            "event_min_consecutive": args.event_min_consecutive,
            "point_events_override_min_flags": 1,
        },
        "detectors": detectors,
    }

    metrics_out = resolve(args.metrics_out)
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=True), encoding="utf-8")
    write_markdown(REPORT_DIR / "ml_demo_summary.md", best)
    print(f"[anomaly-benchmark] wrote {metrics_out}")
    print(f"[anomaly-benchmark] best {best['name']} f1={best['overall']['f1']:.4f}")


if __name__ == "__main__":
    main()
