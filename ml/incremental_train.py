"""
Incremental Training — Projet 16
Re-trains LSTM models on new data that arrived since the last checkpoint.
Designed to run as a scheduled job (e.g., daily via cron or Airflow).
"""

import os
import glob
import psycopg2
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

PG_DSN      = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
MODEL_DIR   = os.getenv("MODEL_DIR", "./models")
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "96"))
HORIZON     = int(os.getenv("HORIZON", "4"))
EPOCHS      = int(os.getenv("INCR_EPOCHS", "5"))     # fewer epochs for incremental pass
BATCH_SIZE  = int(os.getenv("BATCH_SIZE", "32"))


def load_new_data(cluster_id: int, since_hours: int = 24):
    sql = """
        SELECT mr.kwh
        FROM meter_readings mr
        JOIN meters m ON mr.meter_id = m.meter_id
        WHERE m.cluster_id = %s
          AND mr.time >= NOW() - INTERVAL '%s hours'
        ORDER BY mr.time;
    """
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (cluster_id, since_hours))
            rows = cur.fetchall()
    return np.array([r[0] for r in rows])


def retrain_cluster(cluster_id: int) -> None:
    path = os.path.join(MODEL_DIR, f"lstm_cluster_{cluster_id}.keras")
    if not os.path.exists(path):
        print(f"[incr] no saved model for cluster {cluster_id}, skipping")
        return

    new_data = load_new_data(cluster_id)
    if len(new_data) < WINDOW_SIZE + HORIZON:
        print(f"[incr] not enough new data for cluster {cluster_id} ({len(new_data)} points)")
        return

    scaler  = MinMaxScaler()
    values  = scaler.fit_transform(new_data.reshape(-1, 1)).flatten()

    X, y    = [], []
    for i in range(len(values) - WINDOW_SIZE - HORIZON + 1):
        X.append(values[i: i + WINDOW_SIZE])
        y.append(values[i + WINDOW_SIZE: i + WINDOW_SIZE + HORIZON])
    X, y = np.array(X).reshape(-1, WINDOW_SIZE, 1), np.array(y)

    model = tf.keras.models.load_model(path)
    model.fit(X, y, epochs=EPOCHS, batch_size=BATCH_SIZE, verbose=0)
    model.save(path)
    print(f"[incr] cluster {cluster_id} updated → {path}")


if __name__ == "__main__":
    model_paths = glob.glob(os.path.join(MODEL_DIR, "lstm_cluster_*.keras"))
    cluster_ids = [int(p.split("_")[-1].replace(".keras", "")) for p in model_paths]
    for cid in cluster_ids:
        retrain_cluster(cid)
