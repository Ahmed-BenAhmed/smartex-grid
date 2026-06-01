"""Compare anomaly-detector operating points for the report.

The output makes the precision/recall tradeoff explicit instead of treating a
single MAD threshold as a fixed truth.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from eval_anomaly_detection import DEFAULT_INPUT, REPORT_DIR, evaluate, write_markdown  # noqa: E402


def build_table(rows: list[dict]) -> str:
    lines = [
        "| Seuil MAD | Precision | Recall | F1 | TP | FP | FN | TN |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        overall = item["overall"]
        lines.append(
            "| "
            f"{item['mad_multiplier']:.1f} | "
            f"{overall['precision']:.4f} | "
            f"{overall['recall']:.4f} | "
            f"{overall['f1']:.4f} | "
            f"{overall['tp']} | {overall['fp']} | {overall['fn']} | {overall['tn']} |"
        )
    return "\n".join(lines) + "\n"


def default_thresholds() -> list[float]:
    return [round(0.5 + step * 0.1, 1) for step in range(46)]


def best_operating_point(rows: list[dict], min_precision: float) -> dict:
    eligible = [row for row in rows if row["overall"]["precision"] >= min_precision]
    candidates = eligible or rows
    return max(
        candidates,
        key=lambda row: (
            row["overall"]["recall"],
            row["overall"]["f1"],
            -row["mad_multiplier"],
        ),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["mad_multiplier", "precision", "recall", "f1", "tp", "fp", "fn", "tn"],
        )
        writer.writeheader()
        for item in rows:
            overall = item["overall"]
            writer.writerow(
                {
                    "mad_multiplier": item["mad_multiplier"],
                    "precision": overall["precision"],
                    "recall": overall["recall"],
                    "f1": overall["f1"],
                    "tp": overall["tp"],
                    "fp": overall["fp"],
                    "fn": overall["fn"],
                    "tn": overall["tn"],
                }
            )


def write_plot(path: Path, rows: list[dict], best: dict) -> None:
    width, height = 1100, 560
    left, right, top, bottom = 86, 44, 64, 82
    plot_w = width - left - right
    plot_h = height - top - bottom
    min_x = min(row["mad_multiplier"] for row in rows)
    max_x = max(row["mad_multiplier"] for row in rows)

    def x_pos(value: float) -> float:
        return left + ((value - min_x) / (max_x - min_x)) * plot_w

    def y_pos(value: float) -> float:
        return top + (1.0 - value) * plot_h

    series = [
        ("Precision", "#2d936c", [row["overall"]["precision"] for row in rows]),
        ("Recall", "#2f80ed", [row["overall"]["recall"] for row in rows]),
        ("F1", "#d9822b", [row["overall"]["f1"] for row in rows]),
    ]
    grid = []
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        y = y_pos(tick)
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#d8dee9" stroke-width="1"/>')
        grid.append(f'<text x="{left-14}" y="{y+6:.1f}" text-anchor="end" class="small">{tick:.2f}</text>')
    for tick in [0.5, 1, 2, 3, 4, 5]:
        x = x_pos(tick)
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" stroke="#edf0f5" stroke-width="1"/>')
        grid.append(f'<text x="{x:.1f}" y="{height-bottom+34}" text-anchor="middle" class="small">{tick:g}</text>')

    paths = []
    xs = [row["mad_multiplier"] for row in rows]
    for label, color, values in series:
        points = " ".join(f"{x_pos(x):.1f},{y_pos(y):.1f}" for x, y in zip(xs, values))
        dots = "\n".join(
            f'<circle cx="{x_pos(x):.1f}" cy="{y_pos(y):.1f}" r="3.2" fill="{color}"/>'
            for x, y in zip(xs, values)
        )
        paths.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>\n{dots}')

    best_x = x_pos(best["mad_multiplier"])
    legend_items = []
    lx = left
    for label, color, _values in series:
        legend_items.append(f'<rect x="{lx}" y="510" width="22" height="8" rx="4" fill="{color}"/>')
        legend_items.append(f'<text x="{lx+32}" y="518" class="small">{label}</text>')
        lx += 150

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#fbfaf6"/>
  <style>
    text {{ font-family: DejaVu Sans, Arial, sans-serif; fill: #14213d; }}
    .title {{ font-size: 32px; font-weight: 700; }}
    .axis {{ font-size: 22px; font-weight: 700; }}
    .small {{ font-size: 18px; }}
  </style>
  <text x="{width/2}" y="36" text-anchor="middle" class="title">Balayage du seuil MAD</text>
  {''.join(grid)}
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#14213d" stroke-width="2"/>
  <line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#14213d" stroke-width="2"/>
  <line x1="{best_x:.1f}" y1="{top}" x2="{best_x:.1f}" y2="{height-bottom}" stroke="#14213d" stroke-width="2" stroke-dasharray="8 8"/>
  <text x="{best_x+10:.1f}" y="{top+24}" class="small">seuil retenu = {best["mad_multiplier"]:.1f}</text>
  {''.join(paths)}
  <text x="{width/2}" y="{height-22}" text-anchor="middle" class="axis">Seuil MAD</text>
  <text x="26" y="{height/2}" text-anchor="middle" transform="rotate(-90 26 {height/2})" class="axis">Score</text>
  {''.join(legend_items)}
</svg>
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare MAD thresholds on injected anomaly labels.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT))
    parser.add_argument("--thresholds", nargs="+", type=float, default=None)
    parser.add_argument("--group-by", default="meter_id")
    parser.add_argument("--window", type=int, default=24)
    parser.add_argument("--min-abs-deviation", type=float, default=0.12)
    parser.add_argument("--tolerance-steps", type=int, default=2)
    parser.add_argument("--forecast-file", default=None, help="Forecast CSV used for forecast-residual MAD detection")
    parser.add_argument("--all-input-rows", action="store_true", help="Score rows without a forecast as negatives")
    parser.add_argument("--min-precision", type=float, default=0.95)
    parser.add_argument("--json-out", default=str(REPORT_DIR / "anomaly_threshold_sweep.json"))
    parser.add_argument("--md-out", default=str(REPORT_DIR / "anomaly_threshold_sweep.md"))
    parser.add_argument("--csv-out", default=str(REPORT_DIR / "anomaly_threshold_sweep.csv"))
    parser.add_argument("--plot-out", default=str(REPORT_DIR / "anomaly_threshold_sweep.svg"))
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    forecast_file = Path(args.forecast_file) if args.forecast_file else None
    if forecast_file is not None and not forecast_file.is_absolute():
        forecast_file = ROOT / forecast_file

    thresholds = args.thresholds or default_thresholds()
    rows = [
        evaluate(
            input_path,
            args.group_by,
            args.window,
            threshold,
            args.min_abs_deviation,
            args.tolerance_steps,
            forecast_file=forecast_file,
            forecast_coverage_only=not args.all_input_rows,
        )
        for threshold in thresholds
    ]
    best = best_operating_point(rows, args.min_precision)

    json_out = Path(args.json_out)
    md_out = Path(args.md_out)
    csv_out = Path(args.csv_out)
    plot_out = Path(args.plot_out)
    if not json_out.is_absolute():
        json_out = ROOT / json_out
    if not md_out.is_absolute():
        md_out = ROOT / md_out
    if not csv_out.is_absolute():
        csv_out = ROOT / csv_out
    if not plot_out.is_absolute():
        plot_out = ROOT / plot_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(
            {
                "input_file": str(input_path),
                "forecast_file": str(forecast_file) if forecast_file else None,
                "selection_rule": f"max recall with precision >= {args.min_precision}",
                "best": best,
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    md_out.write_text(build_table(rows), encoding="utf-8")
    write_csv(csv_out, rows)
    write_plot(plot_out, rows, best)
    selected_payload = evaluate(
        input_path,
        args.group_by,
        args.window,
        best["mad_multiplier"],
        args.min_abs_deviation,
        args.tolerance_steps,
        forecast_file=forecast_file,
        forecast_coverage_only=not args.all_input_rows,
    )
    metrics_out = REPORT_DIR / "anomaly_eval_metrics.json"
    metrics_out.write_text(json.dumps(selected_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(REPORT_DIR / "ml_demo_summary.md", selected_payload)
    print(f"[thresholds] wrote {json_out}")
    print(f"[thresholds] wrote {md_out}")
    print(f"[thresholds] wrote {csv_out}")
    print(f"[thresholds] wrote {plot_out}")
    print(
        "[thresholds] best "
        f"MAD={best['mad_multiplier']:.1f} "
        f"precision={best['overall']['precision']:.4f} "
        f"recall={best['overall']['recall']:.4f} "
        f"f1={best['overall']['f1']:.4f}"
    )


if __name__ == "__main__":
    main()
