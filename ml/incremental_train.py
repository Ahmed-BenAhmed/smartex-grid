"""
Incremental Training — SmartGrid
Re-trains LSTM models on new data that arrived since the last checkpoint.
Designed to run as a scheduled job (e.g., daily via cron or Airflow).
"""

import os
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


def safe_model_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_").lower()


def load_new_data(source: str, since_hours: int = 24):
    sql = """
        SELECT kwh
        FROM meter_readings
        WHERE source = %s
          AND time >= NOW() - (%s * INTERVAL '1 hour')
        ORDER BY time;
    """
    with psycopg2.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (source, since_hours))
            rows = cur.fetchall()
    return np.array([r[0] for r in rows])


def retrain_source(source: str) -> None:
    path = os.path.join(MODEL_DIR, f"lstm_source_{safe_model_name(source)}.keras")
    if not os.path.exists(path):
        print(f"[incr] no saved model for source {source}, skipping")
        return

    new_data = load_new_data(source)
    if len(new_data) < WINDOW_SIZE + HORIZON:
        print(f"[incr] not enough new data for source {source} ({len(new_data)} points)")
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
    print(f"[incr] source {source} updated → {path}")


if __name__ == "__main__":
    sources = os.getenv("SOURCES", "")
    if sources:
        source_names = [item.strip() for item in sources.split(",") if item.strip()]
    else:
        source_names = [
            "morocco_high_resolution",
            "london_smart_meters",
            "nigeria_smart_meter",
            "uci_household_power",
        ]
    for source_name in source_names:
        retrain_source(source_name)
