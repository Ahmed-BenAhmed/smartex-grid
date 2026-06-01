"""
Kafka → TimescaleDB consumer.
Reads raw meter readings from Kafka and inserts them into the
TimescaleDB hypertable `meter_readings`.
"""

import json
import os
import psycopg2
from kafka import KafkaConsumer

KAFKA_BROKER  = os.getenv("KAFKA_BROKER",   "localhost:9092")
KAFKA_TOPIC   = os.getenv("KAFKA_TOPIC",    "smartgrid.meters.raw")
KAFKA_GROUP   = os.getenv("KAFKA_GROUP",    "timescale-sink")
PG_DSN        = os.getenv("TIMESCALE_DSN",  "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")

INSERT_SQL = """
    INSERT INTO meter_readings (time, meter_id, kwh, is_anomaly, source)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING;
"""


def main() -> None:
    conn   = psycopg2.connect(PG_DSN)
    cursor = conn.cursor()

    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    print(f"[consumer] listening on {KAFKA_TOPIC}")
    for msg in consumer:
        r = msg.value
        cursor.execute(
            INSERT_SQL,
            (
                r["timestamp"],
                r["meter_id"],
                r["kwh"],
                r.get("is_anomaly", False),
                r.get("source", "kafka_live_replay"),
            ),
        )
        conn.commit()


if __name__ == "__main__":
    main()
