"""
Household clustering — Projet 16
Groups meters into clusters based on consumption patterns
using K-Means on daily load profiles.
One LSTM/Prophet model is trained per cluster.
"""

import numpy as np
import os
import pandas as pd
import json
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover - optional DB dependency
    psycopg2 = None

PG_DSN     = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
N_CLUSTERS = int(os.getenv("N_CLUSTERS", "5"))
ROOT = Path(__file__).resolve().parents[1]
MODEL_READY_DIR = ROOT / "data" / "model_ready"


def load_daily_profiles() -> pd.DataFrame:
    """Load average 15-min slot consumption per meter from TimescaleDB."""
    sql = """
        SELECT
            meter_id,
            EXTRACT(HOUR FROM time) * 4 + FLOOR(EXTRACT(MINUTE FROM time) / 15) AS slot,
            AVG(kwh) AS avg_kwh
        FROM meter_readings
        WHERE time >= NOW() - INTERVAL '30 days'
        GROUP BY meter_id, slot
        ORDER BY meter_id, slot;
    """
    try:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 unavailable")
        with psycopg2.connect(PG_DSN) as conn:
            try:
                df = pd.read_sql(sql, conn)
            except Exception:
                df = pd.DataFrame()
    except Exception:
        df = pd.DataFrame()

    if not df.empty:
        # pivot: rows = meters, cols = 96 time slots
        pivot = df.pivot(index="meter_id", columns="slot", values="avg_kwh").fillna(0)
        return pivot

    # Fallback: build the profiles from local processed/model-ready CSV files.
    frames = []
    local_files = sorted(MODEL_READY_DIR.glob("*_60m.csv"))
    if not local_files:
        local_files = sorted((ROOT / "data" / "processed").glob("*_meter_readings.csv"))

    for path in local_files:
        frames.append(pd.read_csv(path))

    if not frames:
        raise FileNotFoundError("No data available in TimescaleDB or local processed CSV files.")

    cadence_minutes = 60
    metadata_files = sorted(MODEL_READY_DIR.glob("*_metadata.json"))
    if metadata_files:
        try:
            with metadata_files[0].open("r", encoding="utf-8") as mf:
                cadence_minutes = int(json.load(mf).get("target_frequency_minutes", 60))
        except Exception:
            cadence_minutes = 60

    df_local = pd.concat(frames, ignore_index=True)
    df_local["time"] = pd.to_datetime(df_local["time"], errors="coerce")
    df_local = df_local.dropna(subset=["time", "meter_id", "kwh"])
    slot_divisor = max(1, cadence_minutes)
    df_local["slot"] = (df_local["time"].dt.hour * 60 + df_local["time"].dt.minute) // slot_divisor
    df_local = df_local.groupby(["meter_id", "slot"], as_index=False)["kwh"].mean().rename(columns={"kwh": "avg_kwh"})

    # pivot: rows = meters, cols = 96 time slots
    pivot = df_local.pivot(index="meter_id", columns="slot", values="avg_kwh").fillna(0)
    return pivot


def cluster_meters(pivot: pd.DataFrame) -> pd.Series:
    """K-Means clustering on normalized load profiles."""
    scaler  = StandardScaler()
    X       = scaler.fit_transform(pivot.values)
    km      = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    labels  = km.fit_predict(X)
    return pd.Series(labels, index=pivot.index, name="cluster_id")


def save_clusters(clusters: pd.Series) -> None:
    """Persist cluster assignments to the meters table."""
    try:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 unavailable")
        with psycopg2.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                for meter_id, cluster_id in clusters.items():
                    cur.execute(
                        "UPDATE meters SET cluster_id = %s WHERE meter_id = %s",
                        (int(cluster_id), meter_id)
                    )
            conn.commit()
        print(f"[clustering] saved {len(clusters)} cluster assignments")
    except Exception:
        out = MODEL_READY_DIR / "cluster_assignments.csv"
        MODEL_READY_DIR.mkdir(parents=True, exist_ok=True)
        clusters.to_csv(out, header=True)
        print(f"[clustering] DB unavailable, wrote local assignments -> {out}")


if __name__ == "__main__":
    print("[clustering] loading daily profiles...")
    pivot    = load_daily_profiles()
    clusters = cluster_meters(pivot)
    print(clusters.value_counts().sort_index())
    save_clusters(clusters)
