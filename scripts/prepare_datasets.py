"""
Prepare public energy datasets into the project schema:

    time,meter_id,kwh,is_anomaly,source

The script is intentionally streaming-friendly for the London dataset. It writes a
sample by default so local experiments stay fast; pass --max-rows 0 to process all
rows found in the archive.
"""

from __future__ import annotations

import argparse
import csv
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


def normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace(".", "")


def find_column(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {normalize_header(h): h for h in headers}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def prepare_uci(max_rows: int) -> Path:
    archive = RAW_DIR / "individual_household_electric_power_consumption.zip"
    output = PROCESSED_DIR / "uci_meter_readings.csv"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        raise FileNotFoundError(f"Missing {archive}. Run scripts/download_datasets.ps1 first.")

    written = 0
    with zipfile.ZipFile(archive) as zf, output.open("w", newline="", encoding="utf-8") as out:
        txt_name = next(name for name in zf.namelist() if name.endswith(".txt"))
        writer = csv.DictWriter(out, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()

        with zf.open(txt_name) as raw:
            reader = csv.DictReader((line.decode("latin-1") for line in raw), delimiter=";")
            for row in reader:
                active_power = row.get("Global_active_power")
                if not active_power or active_power == "?":
                    continue

                # Dataset value is kW at one-minute granularity, so kWh = kW / 60.
                kwh = float(active_power) / 60.0
                timestamp = datetime.strptime(f"{row['Date']} {row['Time']}", "%d/%m/%Y %H:%M:%S")
                writer.writerow(
                    {
                        "time": timestamp.isoformat(sep=" "),
                        "meter_id": "UCI_HOUSEHOLD_001",
                        "kwh": f"{kwh:.8f}",
                        "is_anomaly": "false",
                        "source": "uci_household_power",
                    }
                )
                written += 1
                if max_rows and written >= max_rows:
                    break

    print(f"[prepare] UCI rows written: {written} -> {output}")
    return output


def parse_london_start_timestamp(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H-%M-%S")


def prepare_london_tsf(zf: zipfile.ZipFile, tsf_name: str, output: Path, max_rows: int) -> int:
    written = 0
    with output.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()

        with zf.open(tsf_name) as raw:
            in_data = False
            for raw_line in raw:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line == "@data":
                    in_data = True
                    continue
                if not in_data or line.startswith("#") or line.startswith("@"):
                    continue

                try:
                    meter_id, start_value, values = line.split(":", 2)
                except ValueError:
                    continue

                start = parse_london_start_timestamp(start_value)
                for offset, value in enumerate(values.split(",")):
                    value = value.strip()
                    if not value or value == "?":
                        continue

                    timestamp = start + timedelta(minutes=30 * offset)
                    writer.writerow(
                        {
                            "time": timestamp.isoformat(sep=" "),
                            "meter_id": meter_id,
                            "kwh": value,
                            "is_anomaly": "false",
                            "source": "london_smart_meters",
                        }
                    )
                    written += 1
                    if max_rows and written >= max_rows:
                        return written

    return written


def prepare_london(max_rows: int) -> Path:
    archive = RAW_DIR / "london_smart_meters_dataset_without_missing_values.zip"
    output = PROCESSED_DIR / "london_meter_readings.csv"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        raise FileNotFoundError(f"Missing {archive}. Run scripts/download_datasets.ps1 first.")

    written = 0
    with zipfile.ZipFile(archive) as zf:
        tsf_names = [name for name in zf.namelist() if name.lower().endswith(".tsf")]
        if tsf_names:
            written = prepare_london_tsf(zf, tsf_names[0], output, max_rows)
            print(f"[prepare] London rows written: {written} -> {output}")
            return output

        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"No CSV files found in {archive}")

    with zipfile.ZipFile(archive) as zf, output.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()

        for csv_name in csv_names:
            with zf.open(csv_name) as raw:
                text_iter = (line.decode("utf-8-sig", errors="replace") for line in raw)
                reader = csv.DictReader(text_iter)
                if not reader.fieldnames:
                    continue

                headers = reader.fieldnames
                meter_col = find_column(headers, ("lclid", "meter_id", "household_id", "id"))
                time_col = find_column(headers, ("tstp", "timestamp", "time", "datetime", "date_time"))
                kwh_col = find_column(headers, ("energy(kwh/halfhour)", "energy_kwh_halfhour", "kwh", "energy"))

                if not meter_col or not time_col or not kwh_col:
                    continue

                for row in reader:
                    value = (row.get(kwh_col) or "").strip()
                    if not value or value.lower() in {"null", "nan"}:
                        continue

                    writer.writerow(
                        {
                            "time": row[time_col],
                            "meter_id": row[meter_col],
                            "kwh": value,
                            "is_anomaly": "false",
                            "source": "london_smart_meters",
                        }
                    )
                    written += 1
                    if max_rows and written >= max_rows:
                        print(f"[prepare] London rows written: {written} -> {output}")
                        return output

    print(f"[prepare] London rows written: {written} -> {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare smart-grid datasets into a common CSV schema.")
    parser.add_argument("--dataset", choices=["london", "uci", "all"], default="all")
    parser.add_argument("--max-rows", type=int, default=100_000, help="Rows per dataset; use 0 for all rows.")
    args = parser.parse_args()

    if args.dataset in {"london", "all"}:
        prepare_london(args.max_rows)
    if args.dataset in {"uci", "all"}:
        prepare_uci(args.max_rows)


if __name__ == "__main__":
    main()
