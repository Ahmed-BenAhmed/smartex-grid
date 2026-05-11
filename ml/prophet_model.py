"""
Prophet Forecasting Model — Projet 16
Alternative to LSTM: uses Facebook Prophet for trend + seasonality.
Run per cluster on daily aggregated data.
"""

import os
import psycopg2
import pandas as pd
import pickle
from prophet import Prophet

PG_DSN     = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
MODEL_DIR  = os.getenv("MODEL_DIR", "./models")
os.makedirs(MODEL_DIR, exist_ok=True)


def load_cluster_daily(cluster_id: int) -> pd.DataFrame:
    sql = """
        SELECT
            md.bucket   AS ds,
            SUM(md.kwh_total) AS y
        FROM meter_daily md
        JOIN meters m ON md.meter_id = m.meter_id
        WHERE m.cluster_id = %s
        GROUP BY md.bucket
        ORDER BY md.bucket;
    """
    with psycopg2.connect(PG_DSN) as conn:
        df = pd.read_sql(sql, conn, params=(cluster_id,))
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def train(cluster_id: int, forecast_days: int = 7) -> pd.DataFrame:
    print(f"[prophet] training cluster {cluster_id}")
    df = load_cluster_daily(cluster_id)
    if df.empty:
        print(f"[prophet] no data for cluster {cluster_id}, skipping")
        return pd.DataFrame()

    m = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=True,
        interval_width=0.95,
    )
    m.fit(df)

    future   = m.make_future_dataframe(periods=forecast_days)
    forecast = m.predict(future)

    path = os.path.join(MODEL_DIR, f"prophet_cluster_{cluster_id}.pkl")
    with open(path, "wb") as f:
        pickle.dump(m, f)
    print(f"[prophet] saved → {path}")

    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(forecast_days)


if __name__ == "__main__":
    import sys
    cluster_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    forecast   = train(cluster_id)
    print(forecast.to_string())
