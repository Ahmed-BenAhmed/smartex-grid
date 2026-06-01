from __future__ import annotations

import csv
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "smartgrid_demo"
COMMANDS = REPORT / "commands"
EVIDENCE = REPORT / "evidence"


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def terminal_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <style>
    body {{
      margin: 0;
      background: #eef3f5;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: #d8dee9;
    }}
    .frame {{
      width: 1180px;
      min-height: 720px;
      margin: 0;
      padding: 32px;
      box-sizing: border-box;
      background: linear-gradient(135deg, #19233a, #0c111d);
    }}
    .bar {{
      height: 38px;
      border-radius: 8px 8px 0 0;
      background: #243047;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 14px;
      color: #a8b3cf;
      font-family: Inter, Arial, sans-serif;
      font-size: 14px;
    }}
    .dot {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; }}
    .red {{ background: #ff5f57; }}
    .yellow {{ background: #febc2e; }}
    .green {{ background: #28c840; }}
    .title {{ margin-left: 10px; }}
    pre {{
      margin: 0;
      padding: 22px;
      min-height: 610px;
      white-space: pre-wrap;
      word-break: break-word;
      background: #111827;
      border: 1px solid #34405a;
      border-top: none;
      border-radius: 0 0 8px 8px;
      font-size: 17px;
      line-height: 1.45;
    }}
    .prompt {{ color: #6ee7b7; }}
  </style>
</head>
<body>
  <div class="frame">
    <div class="bar">
      <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
      <span class="title">{html.escape(title)}</span>
    </div>
    <pre>{html.escape(body)}</pre>
  </div>
</body>
</html>
"""


def line_points(rows: list[dict], key: str, max_points: int = 96) -> str:
    selected = [r for r in rows if r["group_key"] == key and str(r.get("fold", "")) == "5"]
    selected = selected[:max_points]
    if not selected:
        return ""
    actual = [float(r["actual"]) for r in selected]
    forecast = [float(r["forecast"]) for r in selected]
    values = actual + forecast
    lo, hi = min(values), max(values)
    span = max(hi - lo, 1e-9)

    def pts(series: list[float]) -> str:
        out = []
        for idx, value in enumerate(series):
            x = 45 + idx * (700 / max(len(series) - 1, 1))
            y = 250 - ((value - lo) / span) * 190
            out.append(f"{x:.1f},{y:.1f}")
        return " ".join(out)

    return f"""
      <polyline points="{pts(actual)}" fill="none" stroke="#22b8c8" stroke-width="4" />
      <polyline points="{pts(forecast)}" fill="none" stroke="#233b7b" stroke-width="4" stroke-dasharray="8 8" />
    """


def dashboard_page() -> str:
    forecast = json.loads((ROOT / "reports" / "ml" / "forecast_metrics.json").read_text())
    anomaly = json.loads((ROOT / "reports" / "ml" / "anomaly_eval_metrics.json").read_text())
    primary_forecast = ROOT / forecast["primary_forecast_file"]
    with primary_forecast.open() as handle:
        forecast_rows = list(csv.DictReader(handle))

    primary_model = next(item for item in forecast["models"] if item["name"] == forecast["primary_model"])
    overall_f = primary_model["overall"]
    overall_a = anomaly.get("best_overall", anomaly.get("overall", {}))
    best_detector = anomaly.get("best_detector", "")
    best_payload = next((item for item in anomaly.get("detectors", []) if item.get("name") == best_detector), anomaly)
    groups = best_payload.get("groups", anomaly.get("groups", {}))
    group_keys = sorted({row["group_key"] for row in forecast_rows})
    svg_a = line_points(forecast_rows, group_keys[0]) if group_keys else ""
    svg_b = line_points(forecast_rows, group_keys[1]) if len(group_keys) > 1 else ""

    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <style>
    body {{
      margin: 0;
      background: #f4f7f8;
      font-family: Inter, Arial, sans-serif;
      color: #17223b;
      overflow: hidden;
    }}
    .page {{ width: 1260px; height: 880px; padding: 28px; box-sizing: border-box; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; color: #233b7b; }}
    .sub {{ color: #546179; margin-bottom: 18px; font-size: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 14px; }}
    .card {{
      background: white;
      border: 1px solid #d9e5e8;
      border-radius: 8px;
      padding: 15px;
      box-shadow: 0 8px 20px rgba(20, 43, 67, 0.08);
    }}
    .label {{ color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; }}
    .value {{ color: #233b7b; font-size: 32px; font-weight: 800; margin-top: 6px; }}
    .wide {{ grid-column: span 2; }}
    .chart {{ background: white; border: 1px solid #d9e5e8; border-radius: 8px; padding: 14px; }}
    svg {{ width: 100%; height: 265px; }}
    .legend {{ display:flex; gap:18px; color:#475569; font-size:14px; margin-top:8px; }}
    .swatch {{ display:inline-block; width:20px; height:4px; vertical-align:middle; margin-right:7px; }}
    table {{ width:100%; border-collapse: collapse; font-size:15px; }}
    th, td {{ border-bottom:1px solid #e2e8f0; padding:10px; text-align:left; }}
    th {{ color:#233b7b; }}
  </style>
</head>
<body>
  <div class="page">
    <h1>SmartGrid ML demo - resultats quantitatifs</h1>
    <div class="sub">Evaluation reproductible a cadence 30 min, split naturel par source et horizon 24h.</div>
    <div class="grid">
      <div class="card"><div class="label">WAPE 1 pas</div><div class="value">{overall_f["wape_1_step"]:.3f}</div></div>
      <div class="card"><div class="label">WAPE 24h</div><div class="value">{overall_f["wape_horizon"]:.3f}</div></div>
      <div class="card"><div class="label">Precision anomalies</div><div class="value">{overall_a["precision"]:.3f}</div></div>
      <div class="card"><div class="label">F1 anomalies</div><div class="value">{overall_a["f1"]:.3f}</div></div>
    </div>
    <div class="grid">
      <div class="chart wide">
        <h2>Forecast vs actual - {html.escape(group_keys[0] if group_keys else "source A")}</h2>
        <svg viewBox="0 0 790 300">
          <line x1="45" y1="250" x2="760" y2="250" stroke="#cbd5e1"/>
          <line x1="45" y1="45" x2="45" y2="250" stroke="#cbd5e1"/>
          {svg_a}
        </svg>
        <div class="legend"><span><i class="swatch" style="background:#22b8c8"></i>actual</span><span><i class="swatch" style="background:#233b7b"></i>forecast</span></div>
      </div>
      <div class="chart wide">
        <h2>Forecast vs actual - {html.escape(group_keys[1] if len(group_keys) > 1 else "source B")}</h2>
        <svg viewBox="0 0 790 300">
          <line x1="45" y1="250" x2="760" y2="250" stroke="#cbd5e1"/>
          <line x1="45" y1="45" x2="45" y2="250" stroke="#cbd5e1"/>
          {svg_b}
        </svg>
        <div class="legend"><span><i class="swatch" style="background:#22b8c8"></i>actual</span><span><i class="swatch" style="background:#233b7b"></i>forecast</span></div>
      </div>
    </div>
    <div class="card">
      <table>
        <tr><th>Groupe</th><th>TP</th><th>FP</th><th>FN</th><th>Precision</th><th>Recall</th><th>F1</th><th>Latence moyenne</th></tr>
        {''.join(f"<tr><td>{html.escape(k)}</td><td>{v['tp']}</td><td>{v['fp']}</td><td>{v['fn']}</td><td>{v['precision']:.3f}</td><td>{v['recall']:.3f}</td><td>{v['f1']:.3f}</td><td>{(v.get('avg_latency_minutes') or 0):.0f} min</td></tr>" for k, v in groups.items())}
      </table>
    </div>
  </div>
</body>
</html>
"""


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for idx, command_file in enumerate(sorted(COMMANDS.glob("*.txt")), start=1):
        content = command_file.read_text(encoding="utf-8", errors="replace")
        title = command_file.stem.replace("_", " ")
        write(EVIDENCE / f"{idx:02d}_{command_file.stem}.html", terminal_page(title, content))
    write(EVIDENCE / "20_ml_dashboard.html", dashboard_page())


if __name__ == "__main__":
    main()
