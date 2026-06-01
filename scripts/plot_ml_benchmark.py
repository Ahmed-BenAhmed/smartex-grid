"""Create report-ready SVG plots from ML benchmark artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "ml"


COLORS = ["#2d936c", "#2f80ed", "#d9822b", "#8e44ad", "#34495e"]


def fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def bar_chart(path: Path, title: str, subtitle: str, labels: list[str], values: list[float], ylabel: str, max_value: float | None = None) -> None:
    width, height = 1100, 620
    left, right, top, bottom = 96, 42, 92, 128
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_y = max_value or max(values + [1.0])
    bar_gap = 18
    bar_w = (plot_w - bar_gap * (len(values) - 1)) / max(len(values), 1)

    bars = []
    for idx, (label, value) in enumerate(zip(labels, values)):
        x = left + idx * (bar_w + bar_gap)
        h = (value / max_y) * plot_h if max_y else 0
        y = top + plot_h - h
        color = COLORS[idx % len(COLORS)]
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" rx="5"/>')
        bars.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="value">{fmt(value)}</text>')
        wrapped = label.replace("_", " ")
        bars.append(
            f'<text x="{x + bar_w/2:.1f}" y="{height - bottom + 32}" text-anchor="middle" class="small">{wrapped}</text>'
        )

    grid = []
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        y = top + plot_h - tick * plot_h
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#d8dee9" stroke-width="1"/>')
        grid.append(f'<text x="{left-12}" y="{y+6:.1f}" text-anchor="end" class="small">{tick * max_y:.2f}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#fbfaf6"/>
  <style>
    text {{ font-family: DejaVu Sans, Arial, sans-serif; fill: #14213d; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 18px; fill: #485163; }}
    .small {{ font-size: 15px; }}
    .value {{ font-size: 16px; font-weight: 700; }}
    .axis {{ font-size: 19px; font-weight: 700; }}
  </style>
  <text x="{width/2}" y="38" text-anchor="middle" class="title">{title}</text>
  <text x="{width/2}" y="66" text-anchor="middle" class="subtitle">{subtitle}</text>
  {''.join(grid)}
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#14213d" stroke-width="2"/>
  <line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#14213d" stroke-width="2"/>
  <text x="28" y="{height/2}" text-anchor="middle" transform="rotate(-90 28 {height/2})" class="axis">{ylabel}</text>
  {''.join(bars)}
</svg>
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def grouped_bar_chart(path: Path, title: str, subtitle: str, labels: list[str], row_values: list[float], event_values: list[float]) -> None:
    width, height = 1200, 620
    left, right, top, bottom = 92, 42, 92, 128
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_y = 1.0
    group_gap = 32
    bar_gap = 8
    group_w = (plot_w - group_gap * (len(labels) - 1)) / max(len(labels), 1)
    bar_w = (group_w - bar_gap) / 2
    bars = []
    for idx, label in enumerate(labels):
        x0 = left + idx * (group_w + group_gap)
        for offset, value, color, series in [
            (0, row_values[idx], "#2f80ed", "row"),
            (bar_w + bar_gap, event_values[idx], "#d9822b", "event"),
        ]:
            h = (value / max_y) * plot_h
            y = top + plot_h - h
            x = x0 + offset
            bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" rx="5"/>')
            bars.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 7:.1f}" text-anchor="middle" class="value">{fmt(value)}</text>')
        bars.append(f'<text x="{x0 + group_w/2:.1f}" y="{height-bottom+32}" text-anchor="middle" class="small">{label.replace("_", " ")}</text>')
    grid = []
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        y = top + plot_h - tick * plot_h
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#d8dee9" stroke-width="1"/>')
        grid.append(f'<text x="{left-12}" y="{y+6:.1f}" text-anchor="end" class="small">{tick:.2f}</text>')
    legend = '''
  <rect x="92" y="548" width="24" height="10" rx="4" fill="#2f80ed"/><text x="126" y="558" class="small">F1 ligne</text>
  <rect x="258" y="548" width="24" height="10" rx="4" fill="#d9822b"/><text x="292" y="558" class="small">F1 événement</text>
'''
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#fbfaf6"/>
  <style>
    text {{ font-family: DejaVu Sans, Arial, sans-serif; fill: #14213d; }}
    .title {{ font-size: 30px; font-weight: 700; }}
    .subtitle {{ font-size: 18px; fill: #485163; }}
    .small {{ font-size: 15px; }}
    .value {{ font-size: 16px; font-weight: 700; }}
    .axis {{ font-size: 19px; font-weight: 700; }}
  </style>
  <text x="{width/2}" y="38" text-anchor="middle" class="title">{title}</text>
  <text x="{width/2}" y="66" text-anchor="middle" class="subtitle">{subtitle}</text>
  {''.join(grid)}
  <line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#14213d" stroke-width="2"/>
  <line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#14213d" stroke-width="2"/>
  <text x="28" y="{height/2}" text-anchor="middle" transform="rotate(-90 28 {height/2})" class="axis">F1</text>
  {''.join(bars)}
  {legend}
</svg>
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot ML benchmark metrics as SVG.")
    parser.add_argument("--matrix", default=str(REPORT_DIR / "experiment_matrix.json"))
    parser.add_argument("--anomaly", default=str(REPORT_DIR / "anomaly_eval_metrics.json"))
    args = parser.parse_args()

    matrix_path = Path(args.matrix)
    if not matrix_path.is_absolute():
        matrix_path = ROOT / matrix_path
    anomaly_path = Path(args.anomaly)
    if not anomaly_path.is_absolute():
        anomaly_path = ROOT / anomaly_path
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    anomaly = json.loads(anomaly_path.read_text(encoding="utf-8"))

    forecasts = [item for item in matrix["experiments"] if item["family"] == "forecast" and item["status"] == "completed"]
    bar_chart(
        REPORT_DIR / "forecast_model_comparison.svg",
        "Benchmark de prévision",
        "Cadence 30 min, split naturel par source, horizon 24h",
        [item["name"] for item in forecasts],
        [item["overall"]["wape_horizon"] for item in forecasts],
        "WAPE horizon",
        max_value=max(item["overall"]["wape_horizon"] for item in forecasts) * 1.1,
    )

    detectors = [item for item in anomaly["detectors"] if item["status"] == "completed"]
    grouped_bar_chart(
        REPORT_DIR / "anomaly_row_vs_event_f1.svg",
        "Détection d'anomalies: ligne vs événement",
        "Scoring événement: k=5 pour segments non ponctuels, k=1 pour pics/drops",
        [item["name"].replace("forecast_residual_mad__", "") for item in detectors],
        [item["overall"]["f1"] for item in detectors],
        [item.get("event_level", {}).get("f1", 0.0) for item in detectors],
    )
    print(f"[plots] wrote {REPORT_DIR / 'forecast_model_comparison.svg'}")
    print(f"[plots] wrote {REPORT_DIR / 'anomaly_row_vs_event_f1.svg'}")


if __name__ == "__main__":
    main()
