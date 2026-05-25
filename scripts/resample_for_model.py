"""
Resample processed meter CSVs into model-ready aggregates.

The processed datasets already conform to the canonical schema:

    time,meter_id,kwh,is_anomaly,source

This script aggregates rows into a coarser cadence, defaulting to hourly.
It keeps the same schema so the output can be loaded into TimescaleDB or fed
directly into offline ML jobs.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
MODEL_READY_DIR = ROOT / "data" / "model_ready"


def parse_timestamp(value: str) -> datetime:
    value = value.strip().replace("Z", "+00:00")
    candidates = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H-%M-%S",
    ]
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        for fmt in candidates:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
    raise ValueError(f"Unsupported timestamp format: {value}")


def floor_bucket(ts: datetime, freq_minutes: int) -> datetime:
    total_minutes = ts.hour * 60 + ts.minute
    bucket_minutes = (total_minutes // freq_minutes) * freq_minutes
    hour = bucket_minutes // 60
    minute = bucket_minutes % 60
    return ts.replace(hour=hour, minute=minute, second=0, microsecond=0)


def resample_file(path: Path, freq_minutes: int) -> Path:
    MODEL_READY_DIR.mkdir(parents=True, exist_ok=True)
    output = MODEL_READY_DIR / f"{path.stem}_{freq_minutes}m.csv"
    meta_output = MODEL_READY_DIR / f"{path.stem}_{freq_minutes}m_metadata.json"

    buckets: dict[tuple[str, str], float] = defaultdict(float)
    meters = set()
    rows_in = 0
    min_ts = None
    max_ts = None

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time", "meter_id", "kwh", "is_anomaly", "source"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")

        for row in reader:
            rows_in += 1
            ts = parse_timestamp(row["time"])
            bucket = floor_bucket(ts, freq_minutes)
            meter_id = row["meter_id"].strip()
            source = row.get("source", path.stem).strip() or path.stem
            kwh = float(row["kwh"])
            buckets[(bucket.isoformat(sep=" "), meter_id, source)] += kwh
            meters.add(meter_id)

            if min_ts is None or ts.isoformat(sep=" ") < min_ts:
                min_ts = ts.isoformat(sep=" ")
            if max_ts is None or ts.isoformat(sep=" ") > max_ts:
                max_ts = ts.isoformat(sep=" ")

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()

        for (time_bucket, meter_id, source), total_kwh in sorted(buckets.items()):
            writer.writerow(
                {
                    "time": time_bucket,
                    "meter_id": meter_id,
                    "kwh": f"{total_kwh:.8f}",
                    "is_anomaly": "false",
                    "source": source,
                }
            )

    with meta_output.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "input_file": str(path),
                "output_file": str(output),
                "rows_in": rows_in,
                "rows_out": len(buckets),
                "distinct_meters": len(meters),
                "start_timestamp": min_ts,
                "end_timestamp": max_ts,
                "target_frequency_minutes": freq_minutes,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )

    print(f"[resample] {path.name} -> {output.name} ({len(buckets)} rows)")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Resample processed smart-meter CSVs to a canonical cadence.")
    parser.add_argument("files", nargs="*", help="Processed CSV files to resample. Defaults to all *_meter_readings.csv files.")
    parser.add_argument("--freq-minutes", type=int, default=60, help="Target cadence in minutes (default: 60).")
    args = parser.parse_args()

    if args.files:
        files = [Path(f) if Path(f).is_absolute() else ROOT / f for f in args.files]
    else:
        files = sorted(PROCESSED_DIR.glob("*_meter_readings.csv"))

    if not files:
        raise FileNotFoundError(f"No processed meter CSV files found in {PROCESSED_DIR}")

    for path in files:
        resample_file(path, args.freq_minutes)


if __name__ == "__main__":
    main()
