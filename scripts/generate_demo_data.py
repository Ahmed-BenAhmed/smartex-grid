"""Generate a tiny deterministic smart-meter demo dataset.

The output is a canonical processed CSV that can be resampled by
scripts/resample_for_model.py. It is intentionally small and committed only as
a generated runtime artifact under ignored data directories.
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "demo_meter_readings.csv"


def daily_shape(hour: int) -> float:
    morning = 0.55 * math.exp(-((hour - 8) ** 2) / 18)
    evening = 0.85 * math.exp(-((hour - 19) ** 2) / 14)
    return 0.7 + morning + evening


def generate_rows(days: int) -> list[dict]:
    start = datetime(2023, 1, 1, 0, 0, 0)
    rows = []
    meters = [("DEMO_METER_A", 1.0), ("DEMO_METER_B", 1.25)]
    for step in range(days * 24):
        ts = start + timedelta(hours=step)
        weekday_factor = 1.08 if ts.weekday() < 5 else 0.92
        for meter_id, meter_factor in meters:
            deterministic_noise = 0.03 * math.sin(step / 3.0 + meter_factor)
            kwh = max(0.05, daily_shape(ts.hour) * weekday_factor * meter_factor + deterministic_noise)
            rows.append(
                {
                    "time": ts.isoformat(sep=" "),
                    "meter_id": meter_id,
                    "kwh": f"{kwh:.8f}",
                    "is_anomaly": "false",
                    "source": "demo_synthetic",
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic demo smart-meter data.")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows(args.days)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[demo-data] wrote {output} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
