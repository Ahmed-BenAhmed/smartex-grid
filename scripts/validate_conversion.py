"""
Validate amperes-to-kW assumptions using the Nigeria smart-meter dataset.

The dataset already includes kWh, voltage_v, current_a, and power_factor.
This script estimates kW from the interval energy values, compares it to the
electrical estimate V * I * PF / 1000, and reports the implied factor.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import csv
import statistics


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "validation"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def infer_period_hours(timestamps: list[str]) -> float:
    if len(timestamps) < 2:
        return 1.0
    times = [datetime.fromisoformat(ts) for ts in timestamps[:10] if ts]
    if len(times) < 2:
        return 1.0
    deltas = [
        (times[i + 1] - times[i]).total_seconds() / 3600.0
        for i in range(len(times) - 1)
        if times[i + 1] > times[i]
    ]
    return statistics.median(deltas) if deltas else 1.0


def main() -> None:
    try:
        from datasets import load_dataset
    except Exception as exc:
        raise RuntimeError("Install 'datasets' first: pip install datasets") from exc

    ds = load_dataset("electricsheepafrica/nigerian_energy_and_utilities_household_smart_meter")["train"]

    per_meter_timestamps: dict[str, list[str]] = defaultdict(list)
    rows = []
    for row in ds:
        meter = row["meter_id"]
        per_meter_timestamps[meter].append(row["timestamp"])
        rows.append(row)

    sample_meter = next(iter(per_meter_timestamps))
    period_hours = infer_period_hours(per_meter_timestamps[sample_meter])

    implied_factors = []
    current_factors = []
    by_disco = defaultdict(list)

    for row in rows:
        current_a = row.get("current_a") or 0.0
        voltage_v = row.get("voltage_v") or 0.0
        pf = row.get("power_factor") or 0.0
        kwh = row.get("consumption_kwh") or 0.0
        if current_a <= 0 or voltage_v <= 0 or pf <= 0:
            continue

        estimated_kw = kwh / period_hours
        electrical_kw = voltage_v * current_a * pf / 1000.0
        implied = estimated_kw / current_a
        current_factor = electrical_kw / current_a
        implied_factors.append(implied)
        current_factors.append(current_factor)
        by_disco[row["disco"]].append(implied)

    out = REPORT_DIR / "ampere_conversion.md"
    with out.open("w", encoding="utf-8") as f:
        f.write("# Nigeria Ampere Conversion Validation\n\n")
        f.write(f"rows: {len(rows)}\n\n")
        f.write(f"meters: {len(per_meter_timestamps)}\n\n")
        f.write(f"inferred_sampling_hours: {period_hours:.4f}\n\n")
        f.write(f"median_implied_factor_kw_per_a: {statistics.median(implied_factors):.4f}\n\n")
        f.write(f"median_electrical_factor_kw_per_a: {statistics.median(current_factors):.4f}\n\n")
        f.write(f"recommended_global_factor_from_formula: {statistics.median(current_factors):.4f}\n\n")
        f.write("## By Disco\n\n")
        for disco, vals in sorted(by_disco.items()):
            f.write(f"- {disco}: median_factor={statistics.median(vals):.4f}, n={len(vals)}\n")

    print(f"[validate] wrote {out}")


if __name__ == "__main__":
    main()
