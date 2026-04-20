"""
Household clustering — Projet 16
Groups meters into clusters based on consumption patterns
using K-Means on daily load profiles.
One LSTM/Prophet model is trained per cluster.
"""

import numpy as np
import os
import psycopg2
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

PG_DSN     = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
N_CLUSTERS = int(os.getenv("N_CLUSTERS", "5"))


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
    with psycopg2.connect(PG_DSN) as conn:
        df = pd.read_sql(sql, conn)

    # pivot: rows = meters, cols = 96 time slots
    pivot = df.pivot(index="meter_id", columns="slot", values="avg_kwh").fillna(0)
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
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            for meter_id, cluster_id in clusters.items():
                cur.execute(
                    "UPDATE meters SET cluster_id = %s WHERE meter_id = %s",
                    (int(cluster_id), meter_id)
                )
        conn.commit()
    print(f"[clustering] saved {len(clusters)} cluster assignments")


if __name__ == "__main__":
    print("[clustering] loading daily profiles...")
    pivot    = load_daily_profiles()
    clusters = cluster_meters(pivot)
    print(clusters.value_counts().sort_index())
    save_clusters(clusters)
