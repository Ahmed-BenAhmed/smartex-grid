"""
Prophet Forecasting Model — SmartGrid
Alternative to LSTM: uses Facebook Prophet for trend + seasonality.
Runs per source/profile on daily aggregated data.
"""

import os
import psycopg2
import pandas as pd
import pickle
from prophet import Prophet

PG_DSN     = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
MODEL_DIR  = os.getenv("MODEL_DIR", "./models")
os.makedirs(MODEL_DIR, exist_ok=True)


def safe_model_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_").lower()


def load_source_daily(source: str) -> pd.DataFrame:
    sql = """
        SELECT
            time_bucket('1 day', time) AS ds,
            SUM(kwh) AS y
        FROM meter_readings
        WHERE source = %s
        GROUP BY ds
        ORDER BY ds;
    """
    with psycopg2.connect(PG_DSN) as conn:
        df = pd.read_sql(sql, conn, params=(source,))
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def train(source: str, forecast_days: int = 7) -> pd.DataFrame:
    print(f"[prophet] training source {source}")
    df = load_source_daily(source)
    if df.empty:
        print(f"[prophet] no data for source {source}, skipping")
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

    path = os.path.join(MODEL_DIR, f"prophet_source_{safe_model_name(source)}.pkl")
    with open(path, "wb") as f:
        pickle.dump(m, f)
    print(f"[prophet] saved → {path}")

    return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(forecast_days)


if __name__ == "__main__":
    import sys
    source_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SOURCE", "morocco_high_resolution")
    forecast   = train(source_name)
    print(forecast.to_string())
