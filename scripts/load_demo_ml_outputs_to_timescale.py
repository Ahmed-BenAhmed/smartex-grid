from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


ROOT = Path(__file__).resolve().parents[1]
PG_DSN = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
DEMO_SOURCES = (
    "morocco_high_resolution",
    "london_smart_meters",
    "nigeria_smart_meter",
    "uci_household_power",
)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_predictions(cursor, path: Path) -> int:
    rows: list[tuple[str, str, str, float, float, float]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            forecast = float(row["forecast"])
            rows.append((
                row["time"],
                row["group_key"],
                row.get("model_type") or "demo_forecast",
                forecast,
                forecast * 0.9,
                forecast * 1.1,
            ))

    if rows:
        execute_values(
            cursor,
            """
            INSERT INTO meter_predictions
                (time, meter_id, model, kwh_pred, kwh_lower, kwh_upper)
            VALUES %s
            """,
            rows,
        )
    return len(rows)


def load_anomalies(cursor, path: Path) -> int:
    rows: list[tuple[str, str, float, float, float, str]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not parse_bool(row["is_anomaly"]):
                continue
            actual = float(row["kwh"])
            expected = actual / 1.75
            deviation = actual - expected
            severity = "high" if deviation > 1.0 else "medium"
            event_key = row.get("source") or row["meter_id"]
            rows.append((event_key, row["time"], actual, expected, deviation, severity))

    if rows:
        execute_values(
            cursor,
            """
            INSERT INTO anomaly_events
                (meter_id, reading_time, kwh_actual, kwh_expected, deviation, severity)
            VALUES %s
            """,
            rows,
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load demo ML outputs into TimescaleDB dashboard tables.")
    parser.add_argument(
        "--forecast-csv",
        default="reports/ml/forecasts/demo_meter_readings_30m_forecasts.csv",
    )
    parser.add_argument(
        "--anomalies-csv",
        default="data/model_ready/demo_meter_readings_30m_injected_forecast_residual_anomalies.csv",
    )
    args = parser.parse_args()

    forecast_csv = ROOT / args.forecast_csv
    anomalies_csv = ROOT / args.anomalies_csv

    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM meter_predictions WHERE meter_id = ANY(%s)", (list(DEMO_SOURCES),))
            cursor.execute("DELETE FROM anomaly_events WHERE meter_id = ANY(%s)", (list(DEMO_SOURCES),))
            cursor.execute(
                "DELETE FROM anomaly_events WHERE meter_id = ANY(%s)",
                (["MOROCCO_SOURCE", "LONDON_SOURCE", "NIGERIA_SOURCE", "UCI_SOURCE"],),
            )
            prediction_count = load_predictions(cursor, forecast_csv)
            anomaly_count = load_anomalies(cursor, anomalies_csv)
        conn.commit()

    print(f"[demo-db] loaded {prediction_count} predictions from {forecast_csv}")
    print(f"[demo-db] loaded {anomaly_count} anomaly events from {anomalies_csv}")


if __name__ == "__main__":
    main()
