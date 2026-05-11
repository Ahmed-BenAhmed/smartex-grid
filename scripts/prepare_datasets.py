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


def prepare_morocco(max_rows: int) -> Path:
    """Prepare the UCI Morocco high-resolution smart-meter dataset.

    The UCI archive may contain an Excel file or CSVs. This function looks for
    a CSV first, otherwise attempts to find an .xlsx/.xls and raises a clear
    error if unsupported. Each row is normalized to the common schema.
    """
    archive = RAW_DIR / "morocco_high_resolution_smart_meters.zip"
    output = PROCESSED_DIR / "morocco_meter_readings.csv"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        raise FileNotFoundError(f"Missing {archive}. Run scripts/download_datasets.ps1 first.")

    written = 0
    # The UCI archive may contain CSV or Excel files; we'll handle both below.
    with zipfile.ZipFile(archive) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]

    # The archive we have contains Excel files (xlsx). Use pandas/openpyxl if available
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "Preparing the Morocco dataset requires pandas and openpyxl. "
            "Please install them (pip install pandas openpyxl) and re-run."
        ) from exc

    with zipfile.ZipFile(archive) as zf, output.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["time", "meter_id", "kwh", "is_anomaly", "source"])
        writer.writeheader()

        # Process each Excel file in the archive
        xlsx_names = [name for name in zf.namelist() if name.lower().endswith(('.xlsx', '.xls'))]
        for xname in xlsx_names:
            # read into pandas from bytes buffer
            with zf.open(xname) as raw:
                data = raw.read()
                from io import BytesIO
                bio = BytesIO(data)
                try:
                    df = pd.read_excel(bio, engine="openpyxl")
                except Exception:
                    # Try without specifying engine
                    bio.seek(0)
                    df = pd.read_excel(bio)

                # Normalize column names
                cols = {c: normalize_header(str(c)) for c in df.columns}
                df.rename(columns=cols, inplace=True)

                # find time column and value columns. Many sheets have a first
                # column like 'DateTime' and subsequent columns per zone (zone1,
                # zone2, ...). We'll melt those into the long format expected by
                # the project: time, meter_id, kwh, is_anomaly, source.
                time_col = find_column(list(df.columns), ("timestamp", "time", "datetime", "date", "date_time", "datetime"))
                if not time_col:
                    continue

                # value columns are all columns except the time column
                value_cols = [c for c in df.columns if c != time_col]
                if not value_cols:
                    continue

                # infer sampling minutes from filename (e.g., '30T' or '10T')
                minutes = None
                lower_name = xname.lower()
                if "30t" in lower_name or "30min" in lower_name:
                    minutes = 30
                elif "10t" in lower_name or "10min" in lower_name:
                    minutes = 10
                else:
                    # fallback: try to infer from differences between first two timestamps
                    try:
                        ts = pd.to_datetime(df[time_col])
                        if len(ts) >= 2:
                            minutes = int((ts.iloc[1] - ts.iloc[0]).total_seconds() / 60)
                    except Exception:
                        minutes = 10

                period_hours = (minutes or 10) / 60.0

                # Melt dataframe: create (time, zone, value)
                melted = df.melt(id_vars=[time_col], value_vars=value_cols, var_name="zone", value_name="value")
                # iterate and write rows; assume numeric 'value' is power in kW
                # so kWh = kW * period_hours. This is documented but should be
                # verified for correctness.
                for row_idx, row in melted.iterrows():
                    k_val = row["value"]
                    if pd.isna(k_val):
                        continue
                    try:
                        # convert to float and to kWh
                        k_float = float(k_val)
                        kwh = k_float * period_hours
                    except Exception:
                        # skip non-numeric
                        continue

                    t_val = row[time_col]
                    # ensure ISO string for timestamp
                    try:
                        t_iso = pd.to_datetime(t_val).isoformat(sep=" ")
                    except Exception:
                        t_iso = str(t_val)

                    meter_id = f"{Path(xname).stem}_{normalize_header(str(row['zone']))}"
                    writer.writerow({
                        "time": t_iso,
                        "meter_id": meter_id,
                        "kwh": f"{kwh:.8f}",
                        "is_anomaly": "false",
                        "source": "morocco_high_resolution",
                    })
                    written += 1
                    if max_rows and written >= max_rows:
                        print(f"[prepare] Morocco rows written: {written} -> {output}")
                        return output

    print(f"[prepare] Morocco rows written: {written} -> {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare smart-grid datasets into a common CSV schema.")
    parser.add_argument("--dataset", choices=["london", "uci", "morocco", "all"], default="all")
    parser.add_argument("--max-rows", type=int, default=100_000, help="Rows per dataset; use 0 for all rows.")
    args = parser.parse_args()

    if args.dataset in {"london", "all"}:
        prepare_london(args.max_rows)
    if args.dataset in {"uci", "all"}:
        prepare_uci(args.max_rows)
    if args.dataset in {"morocco", "all"}:
        prepare_morocco(args.max_rows)


if __name__ == "__main__":
    main()
