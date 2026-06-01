"""
LSTM Forecasting Model — SmartGrid
Trains one LSTM per source/profile on historical 15-min readings.
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


def safe_model_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_").lower()


def load_source_data(source: str) -> pd.DataFrame:
    sql = """
        SELECT time, kwh
        FROM meter_readings
        WHERE source = %s
          AND time >= NOW() - INTERVAL '90 days'
        ORDER BY time;
    """
    with psycopg2.connect(PG_DSN) as conn:
        df = pd.read_sql(sql, conn, params=(source,))
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


def train(source: str) -> None:
    print(f"[lstm] training source {source}")
    df      = load_source_data(source)
    if df.empty:
        print(f"[lstm] no data for source {source}, skipping")
        return

    scaler  = MinMaxScaler()
    values  = scaler.fit_transform(df[["kwh"]].values)
    window  = adaptive_window(values.flatten())

    X, y    = build_sequences(values.flatten(), window, HORIZON)
    X       = X.reshape(-1, window, 1)

    model   = build_model(window, HORIZON)
    model.fit(X, y, epochs=EPOCHS, batch_size=BATCH_SIZE, validation_split=0.1, verbose=1)

    path    = os.path.join(MODEL_DIR, f"lstm_source_{safe_model_name(source)}.keras")
    model.save(path)
    print(f"[lstm] saved → {path}")


if __name__ == "__main__":
    import sys
    source_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SOURCE", "morocco_high_resolution")
    train(source_name)
