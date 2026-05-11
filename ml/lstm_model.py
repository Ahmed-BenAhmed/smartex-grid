"""
LSTM Forecasting Model — Projet 16
Trains one LSTM per cluster on historical 15-min readings.
Uses adaptive time windowing and supports incremental training.
"""

import numpy as np
import os
import psycopg2
import pandas as pd
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

PG_DSN       = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
MODEL_DIR    = os.getenv("MODEL_DIR", "./models")
WINDOW_SIZE  = int(os.getenv("WINDOW_SIZE", "96"))    # 96 × 15min = 24h lookback
HORIZON      = int(os.getenv("HORIZON", "4"))         # predict next 4 × 15min = 1 hour
EPOCHS       = int(os.getenv("EPOCHS", "20"))
BATCH_SIZE   = int(os.getenv("BATCH_SIZE", "32"))
os.makedirs(MODEL_DIR, exist_ok=True)


def load_cluster_data(cluster_id: int) -> pd.DataFrame:
    sql = """
        SELECT mr.time, mr.kwh
        FROM meter_readings mr
        JOIN meters m ON mr.meter_id = m.meter_id
        WHERE m.cluster_id = %s
          AND mr.time >= NOW() - INTERVAL '90 days'
        ORDER BY mr.time;
    """
    with psycopg2.connect(PG_DSN) as conn:
        df = pd.read_sql(sql, conn, params=(cluster_id,))
    return df


def build_sequences(series: np.ndarray, window: int, horizon: int):
    X, y = [], []
    for i in range(len(series) - window - horizon + 1):
        X.append(series[i: i + window])
        y.append(series[i + window: i + window + horizon])
    return np.array(X), np.array(y)


def build_model(window: int, horizon: int) -> tf.keras.Model:
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(window, 1)),
        tf.keras.layers.LSTM(64, return_sequences=True),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dense(horizon),
    ])
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    return model


def adaptive_window(series: np.ndarray, base_window: int = 96) -> int:
    """
    Adaptive time windowing:
    Increase lookback if recent variance is high (volatile consumption).
    """
    recent_std = np.std(series[-96:]) if len(series) >= 96 else np.std(series)
    global_std = np.std(series)
    ratio      = recent_std / (global_std + 1e-8)
    if ratio > 1.5:
        return min(base_window * 2, 288)   # up to 3 days
    elif ratio < 0.5:
        return max(base_window // 2, 48)   # down to 12 hours
    return base_window


def train(cluster_id: int) -> None:
    print(f"[lstm] training cluster {cluster_id}")
    df      = load_cluster_data(cluster_id)
    if df.empty:
        print(f"[lstm] no data for cluster {cluster_id}, skipping")
        return

    scaler  = MinMaxScaler()
    values  = scaler.fit_transform(df[["kwh"]].values)
    window  = adaptive_window(values.flatten())

    X, y    = build_sequences(values.flatten(), window, HORIZON)
    X       = X.reshape(-1, window, 1)

    model   = build_model(window, HORIZON)
    model.fit(X, y, epochs=EPOCHS, batch_size=BATCH_SIZE, validation_split=0.1, verbose=1)

    path    = os.path.join(MODEL_DIR, f"lstm_cluster_{cluster_id}.keras")
    model.save(path)
    print(f"[lstm] saved → {path}")


if __name__ == "__main__":
    import sys
    cluster_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    train(cluster_id)
