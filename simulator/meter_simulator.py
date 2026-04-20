"""
Smart Meter Simulator — Projet 16
Generates realistic 15-minute electricity consumption readings
per household, with daily/seasonal patterns and anomaly injection.

Publishes to Kafka topic: smartgrid.meters.raw
"""

import argparse
import json
import math
import os
import random
import time
from datetime import datetime, timezone


# ── Household profiles ────────────────────────────────────────────────────────

PROFILES = {
    "residential_family":  {"base_kw": 1.2, "peak_kw": 5.5, "noise": 0.15},
    "residential_single":  {"base_kw": 0.4, "peak_kw": 2.0, "noise": 0.10},
    "small_business":      {"base_kw": 3.0, "peak_kw": 12.0, "noise": 0.25},
    "industrial_light":    {"base_kw": 8.0, "peak_kw": 35.0, "noise": 0.30},
}

ANOMALY_PROB      = 0.005   # 0.5% chance per reading of an anomaly spike
ANOMALY_FACTOR    = 4.0     # anomalous reading = factor × normal


class MeterSimulator:
    """
    Simulates one smart meter at 15-minute granularity.
    Mirrors the LoomSimulator pattern from SmartTex for consistency.
    """

    def __init__(self, meter_id: str, profile: str = "residential_family", seed: int | None = None):
        self.meter_id  = meter_id
        self.profile   = PROFILES[profile]
        self.rng       = random.Random(seed)
        self.tick      = 0   # each tick = 15 minutes

    def sample(self) -> dict:
        """Return one 15-min reading and advance the clock."""
        ts  = datetime.now(timezone.utc).isoformat()
        kwh = self._consumption_kwh()
        reading = {
            "timestamp":  ts,
            "meter_id":   self.meter_id,
            "kwh":        round(kwh, 4),
            "is_anomaly": kwh > self.profile["peak_kw"] * 0.9,
        }
        self.tick += 1
        return reading

    # ── internals ─────────────────────────────────────────────────────────────

    def _consumption_kwh(self) -> float:
        hour_of_day = (self.tick % 96) / 4.0   # 96 ticks per day

        # morning + evening peaks
        morning_peak = 3.0 * math.exp(-0.5 * ((hour_of_day - 7.5) / 1.5) ** 2)
        evening_peak = 4.0 * math.exp(-0.5 * ((hour_of_day - 19.0) / 2.0) ** 2)
        daily_shape  = morning_peak + evening_peak + self.profile["base_kw"]

        # weekly dip on weekends (tick // 96 = day number)
        day = (self.tick // 96) % 7
        weekend_factor = 0.75 if day >= 5 else 1.0

        # seasonal drift (slow sine over ~365 days = 35040 ticks)
        seasonal = 0.15 * math.sin(2 * math.pi * self.tick / 35040)

        power_kw = daily_shape * weekend_factor * (1.0 + seasonal)
        power_kw += self.rng.gauss(0, self.profile["noise"])
        power_kw  = max(power_kw, self.profile["base_kw"] * 0.1)

        # anomaly injection
        if self.rng.random() < ANOMALY_PROB:
            power_kw *= ANOMALY_FACTOR

        # kWh for 15-minute interval = kW × (15/60)
        return power_kw * 0.25


# ── Kafka wiring ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Smart meter simulator → Kafka")
    parser.add_argument("--broker",    default=os.getenv("KAFKA_BROKER",   "localhost:9092"))
    parser.add_argument("--topic",     default=os.getenv("KAFKA_TOPIC",    "smartgrid.meters.raw"))
    parser.add_argument("--meters",    type=int, default=int(os.getenv("NUM_METERS", "20")))
    parser.add_argument("--profile",   default="residential_family", choices=PROFILES.keys())
    parser.add_argument("--interval",  type=float, default=float(os.getenv("PUBLISH_INTERVAL", "1.0")),
                        help="Seconds between publishes (1 s = 1 simulated 15-min tick)")
    parser.add_argument("--seed",      type=int, default=None)
    args = parser.parse_args()

    try:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=args.broker,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    except ImportError:
        print("[warn] kafka-python not installed — printing to stdout instead")
        producer = None

    meters = [
        MeterSimulator(f"MTR_{i:04d}", profile=args.profile, seed=args.seed)
        for i in range(args.meters)
    ]

    print(f"[sim] {args.meters} meters → topic={args.topic}  broker={args.broker}")
    try:
        while True:
            for sim in meters:
                reading = sim.sample()
                if producer:
                    producer.send(args.topic, value=reading, key=reading["meter_id"].encode())
                else:
                    print(json.dumps(reading))
            if producer:
                producer.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[sim] shutting down")
    finally:
        if producer:
            producer.close()


if __name__ == "__main__":
    main()
