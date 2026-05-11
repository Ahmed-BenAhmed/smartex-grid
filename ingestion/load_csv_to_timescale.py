"""
Load prepared dataset CSV files into TimescaleDB.

Expected CSV schema:
    time,meter_id,kwh,is_anomaly,source
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


PG_DSN = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
ROOT = Path(__file__).resolve().parents[1]

INSERT_READINGS_SQL = """
    INSERT INTO meter_readings (time, meter_id, kwh, is_anomaly)
    VALUES %s;
"""

UPSERT_METERS_SQL = """
    INSERT INTO meters (meter_id, profile, location)
    VALUES %s
    ON CONFLICT (meter_id) DO NOTHING;
"""


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_file(conn, path: Path, batch_size: int) -> int:
    inserted = 0
    meters: set[str] = set()
    batch: list[tuple[str, str, float, bool]] = []

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time", "meter_id", "kwh", "is_anomaly"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")

        with conn.cursor() as cursor:
            for row in reader:
                meter_id = row["meter_id"]
                batch.append((row["time"], meter_id, float(row["kwh"]), parse_bool(row["is_anomaly"])))
                meters.add(meter_id)

                if len(batch) >= batch_size:
                    execute_values(cursor, INSERT_READINGS_SQL, batch)
                    inserted += len(batch)
                    batch.clear()

            if batch:
                execute_values(cursor, INSERT_READINGS_SQL, batch)
                inserted += len(batch)

            if meters:
                meter_rows = [(meter_id, "public_dataset", path.stem) for meter_id in sorted(meters)]
                execute_values(cursor, UPSERT_METERS_SQL, meter_rows)

    conn.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Load prepared smart-grid CSV files into TimescaleDB.")
    parser.add_argument(
        "files",
        nargs="*",
        default=[
            str(ROOT / "data" / "processed" / "london_meter_readings.csv"),
            str(ROOT / "data" / "processed" / "uci_meter_readings.csv"),
        ],
    )
    parser.add_argument("--batch-size", type=int, default=10_000)
    args = parser.parse_args()

    with psycopg2.connect(PG_DSN) as conn:
        for file_arg in args.files:
            path = Path(file_arg)
            if not path.is_absolute():
                path = ROOT / path
            count = load_file(conn, path, args.batch_size)
            print(f"[load] inserted {count} rows from {path}")


if __name__ == "__main__":
    main()
