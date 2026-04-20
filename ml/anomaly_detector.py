"""
Anomaly Detector — Projet 16
Detects consumption spikes by comparing actual readings
against LSTM/Prophet predictions. Writes events to TimescaleDB.
"""

import os
import psycopg2
import pandas as pd
import numpy as np

PG_DSN    = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD_STD", "3.0"))   # σ above expected


def detect_and_store() -> None:
    sql_residuals = """
        SELECT
            mr.time,
            mr.meter_id,
            mr.kwh                      AS kwh_actual,
            mp.kwh_pred                 AS kwh_expected,
            ABS(mr.kwh - mp.kwh_pred)   AS residual,
            STDDEV(ABS(mr.kwh - mp.kwh_pred)) OVER (
                PARTITION BY mr.meter_id
                ORDER BY mr.time
                ROWS BETWEEN 95 PRECEDING AND CURRENT ROW
            )                           AS rolling_std
        FROM meter_readings mr
        JOIN meter_predictions mp
          ON mr.meter_id = mp.meter_id
         AND mr.time     = mp.time
        WHERE mr.time >= NOW() - INTERVAL '1 hour'
        ORDER BY mr.time;
    """

    insert_sql = """
        INSERT INTO anomaly_events
            (meter_id, reading_time, kwh_actual, kwh_expected, deviation, severity)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;
    """

    with psycopg2.connect(PG_DSN) as conn:
        df = pd.read_sql(sql_residuals, conn)

        if df.empty:
            print("[anomaly] no residuals found, skipping")
            return

        df["z_score"] = df["residual"] / (df["rolling_std"] + 1e-8)
        anomalies     = df[df["z_score"] > THRESHOLD].copy()

        def severity(z: float) -> str:
            if z > THRESHOLD * 2:
                return "high"
            elif z > THRESHOLD * 1.5:
                return "medium"
            return "low"

        with conn.cursor() as cur:
            for _, row in anomalies.iterrows():
                cur.execute(insert_sql, (
                    row["meter_id"],
                    row["time"],
                    row["kwh_actual"],
                    row["kwh_expected"],
                    row["z_score"],
                    severity(row["z_score"]),
                ))
        conn.commit()

    print(f"[anomaly] {len(anomalies)} spikes detected and stored")


if __name__ == "__main__":
    detect_and_store()
