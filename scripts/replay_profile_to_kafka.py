"""Replay prepared smart-meter profiles into Kafka with fresh timestamps.

The script is intentionally deterministic by default. It reads the canonical
processed/model-ready CSV schema and publishes messages that look live while
preserving the shape of the historical profiles.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "processed" / "demo_meter_readings.csv"
DEFAULT_TOPIC = "smartgrid.meters.raw"


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_rows(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"time", "meter_id", "kwh", "is_anomaly", "source"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        for row in reader:
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def replay_messages(
    rows: Iterable[dict[str, str]],
    *,
    start_time: datetime,
    cadence_seconds: int,
    anomaly_every: int,
    anomaly_factor: float,
) -> Iterable[dict[str, object]]:
    for idx, row in enumerate(rows):
        ts = start_time + timedelta(seconds=idx * cadence_seconds)
        kwh = float(row["kwh"])
        injected = anomaly_every > 0 and idx > 0 and idx % anomaly_every == 0
        if injected:
            kwh = kwh * anomaly_factor
        yield {
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "meter_id": row["meter_id"],
            "kwh": round(kwh, 8),
            "is_anomaly": injected or parse_bool(row["is_anomaly"]),
            "source": row.get("source") or "live_replay",
        }


def publish(messages: Iterable[dict[str, object]], *, broker: str, topic: str, sleep_seconds: float, dry_run: bool) -> int:
    producer = None
    if not dry_run:
        try:
            from kafka import KafkaProducer
        except Exception as exc:
            raise RuntimeError("kafka-python is required; run with `uv run --with kafka-python ...`") from exc
        producer = KafkaProducer(
            bootstrap_servers=broker,
            value_serializer=lambda payload: json.dumps(payload).encode("utf-8"),
        )

    count = 0
    for message in messages:
        line = json.dumps(message, ensure_ascii=False)
        if dry_run:
            print(line)
        else:
            assert producer is not None
            producer.send(topic, message)
        count += 1
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    if producer is not None:
        producer.flush()
        producer.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay prepared smart-meter rows into Kafka with live timestamps.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--broker", default=os.getenv("KAFKA_BROKER", "localhost:9092"))
    parser.add_argument("--topic", default=os.getenv("KAFKA_TOPIC", DEFAULT_TOPIC))
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--cadence-seconds", type=int, default=60)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--anomaly-every", type=int, default=17, help="Inject one spike every N messages; 0 disables injection.")
    parser.add_argument("--anomaly-factor", type=float, default=2.5)
    parser.add_argument("--dry-run", action="store_true", help="Print JSON messages instead of publishing to Kafka.")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.is_absolute():
        path = ROOT / path
    rows = load_rows(path, limit=args.limit)
    start = datetime.now(timezone.utc).replace(microsecond=0)
    messages = replay_messages(
        rows,
        start_time=start,
        cadence_seconds=args.cadence_seconds,
        anomaly_every=args.anomaly_every,
        anomaly_factor=args.anomaly_factor,
    )
    count = publish(messages, broker=args.broker, topic=args.topic, sleep_seconds=args.sleep_seconds, dry_run=args.dry_run)
    target = "stdout" if args.dry_run else f"{args.broker}/{args.topic}"
    print(f"[live-replay] published {count} messages to {target}")


if __name__ == "__main__":
    main()
