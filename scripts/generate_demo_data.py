"""Generate deterministic source-level SmartGrid demo profiles.

The output is a canonical processed CSV that can be resampled by
scripts/resample_for_model.py. Each profile represents a dataset/country source
used by the report demo, not a real individual meter.
"""

from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "demo_meter_readings.csv"


def daily_shape(hour: float, *, morning_peak: float, evening_peak: float, base: float) -> float:
    morning = morning_peak * math.exp(-((hour - 8) ** 2) / 18)
    evening = evening_peak * math.exp(-((hour - 19) ** 2) / 14)
    return base + morning + evening


def generate_rows(days: int, cadence_minutes: int) -> list[dict]:
    start = datetime(2023, 1, 1, 0, 0, 0)
    rows = []
    sources = [
        {
            "meter_id": "MOROCCO_SOURCE",
            "source": "morocco_high_resolution",
            "factor": 1.05,
            "base": 0.62,
            "morning_peak": 0.62,
            "evening_peak": 0.78,
            "phase": 0.2,
        },
        {
            "meter_id": "LONDON_SOURCE",
            "source": "london_smart_meters",
            "factor": 1.18,
            "base": 0.70,
            "morning_peak": 0.48,
            "evening_peak": 1.05,
            "phase": 1.0,
        },
        {
            "meter_id": "NIGERIA_SOURCE",
            "source": "nigeria_smart_meter",
            "factor": 0.92,
            "base": 0.58,
            "morning_peak": 0.35,
            "evening_peak": 0.70,
            "phase": 2.1,
        },
        {
            "meter_id": "UCI_SOURCE",
            "source": "uci_household_power",
            "factor": 0.68,
            "base": 0.42,
            "morning_peak": 0.22,
            "evening_peak": 0.38,
            "phase": 3.4,
        },
    ]
    steps_per_day = int((24 * 60) / cadence_minutes)
    for step in range(days * steps_per_day):
        ts = start + timedelta(minutes=step * cadence_minutes)
        hour = ts.hour + ts.minute / 60
        weekday_factor = 1.08 if ts.weekday() < 5 else 0.92
        for profile in sources:
            deterministic_noise = 0.03 * math.sin(step / 3.0 + profile["phase"])
            slow_variation = 1.0 + 0.05 * math.sin(step / (steps_per_day * 3) + profile["phase"])
            shape = daily_shape(
                hour,
                morning_peak=profile["morning_peak"],
                evening_peak=profile["evening_peak"],
                base=profile["base"],
            )
            interval_hours = cadence_minutes / 60
            kwh = max(0.05, (shape * weekday_factor * profile["factor"] * slow_variation + deterministic_noise) * interval_hours)
            rows.append(
                {
                    "time": ts.isoformat(sep=" "),
                    "meter_id": profile["meter_id"],
                    "kwh": f"{kwh:.8f}",
                    "is_anomaly": "false",
                    "source": profile["source"],
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic demo smart-meter data.")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--cadence-minutes", type=int, default=30)
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows(args.days, args.cadence_minutes)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[demo-data] wrote {output} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
