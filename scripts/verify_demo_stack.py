from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2


PG_DSN = os.getenv("TIMESCALE_DSN", "postgresql://smartgrid:smartgrid@localhost:5432/smartgrid")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3001")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9091")
KAFKA_UI_URL = os.getenv("KAFKA_UI_URL", "http://localhost:8080")


@dataclass
class Check:
    name: str
    ok: bool
    details: str


def request_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None, auth: bool = False) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if auth:
        token = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=10) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else None


def request_status(url: str, *, auth: bool = False) -> int:
    headers = {}
    if auth:
        token = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASSWORD}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=10) as response:
        response.read()
        return response.status


def check_http() -> list[Check]:
    checks: list[Check] = []
    endpoints = [
        ("Grafana health", f"{GRAFANA_URL}/api/health", True),
        ("Kafka UI", KAFKA_UI_URL, False),
        ("Prometheus ready", f"{PROMETHEUS_URL}/-/ready", False),
    ]
    for name, url, auth in endpoints:
        try:
            status = request_status(url, auth=auth)
            checks.append(Check(name, status in {200, 302}, f"HTTP {status}"))
        except (HTTPError, URLError, TimeoutError) as exc:
            checks.append(Check(name, False, str(exc)))
    return checks


def check_timescale() -> list[Check]:
    demo_sources = "('morocco_high_resolution', 'london_smart_meters', 'nigeria_smart_meter', 'uci_household_power')"
    queries = {
        "meter_readings": f"SELECT count(*) FROM meter_readings WHERE source IN {demo_sources}",
        "meter_sources": f"SELECT count(DISTINCT source) FROM meter_readings WHERE source IN {demo_sources}",
        "meter_hourly": "SELECT count(*) FROM meter_hourly WHERE meter_id IN ('MOROCCO_SOURCE', 'LONDON_SOURCE', 'NIGERIA_SOURCE', 'UCI_SOURCE')",
        "meter_daily": "SELECT count(*) FROM meter_daily WHERE meter_id IN ('MOROCCO_SOURCE', 'LONDON_SOURCE', 'NIGERIA_SOURCE', 'UCI_SOURCE')",
        "meter_predictions": f"SELECT count(*) FROM meter_predictions WHERE meter_id IN {demo_sources}",
        "anomaly_events": f"SELECT count(*) FROM anomaly_events WHERE meter_id IN {demo_sources}",
    }
    expected = {
        "meter_readings": 4032,
        "meter_sources": 4,
        "meter_hourly": 2016,
        "meter_daily": 84,
        "meter_predictions": 960,
        "anomaly_events": None,
    }
    checks: list[Check] = []
    try:
        with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cursor:
            for name, sql in queries.items():
                cursor.execute(sql)
                count = cursor.fetchone()[0]
                expected_count = expected[name]
                ok = count > 0 if expected_count is None else count == expected_count
                checks.append(Check(f"Timescale {name}", ok, f"{count} rows"))
    except Exception as exc:
        checks.append(Check("Timescale connection", False, str(exc)))
    return checks


def grafana_datasource_uid(name: str) -> tuple[str, str]:
    datasources = request_json(f"{GRAFANA_URL}/api/datasources", auth=True)
    for datasource in datasources:
        if datasource["name"] == name:
            return datasource["uid"], datasource["type"]
    raise RuntimeError(f"missing Grafana datasource: {name}")


def check_grafana_queries() -> list[Check]:
    checks: list[Check] = []
    try:
        dashboard = request_json(f"{GRAFANA_URL}/api/dashboards/uid/smartgrid-load-map", auth=True)["dashboard"]
        checks.append(Check("Grafana dashboard", dashboard["uid"] == "smartgrid-load-map", dashboard["title"]))
        checks.append(Check("Grafana demo time range", dashboard["time"]["from"].startswith("2023-01-01"), str(dashboard["time"])))

        timescale_uid, timescale_type = grafana_datasource_uid("TimescaleDB")
        query = {
            "from": "1672531200000",
            "to": "1674345600000",
            "queries": [
                {
                    "refId": "A",
                    "datasource": {"type": timescale_type, "uid": timescale_uid},
                    "rawSql": "SELECT bucket AS time, SUM(kwh_total) AS kwh FROM meter_hourly WHERE $__timeFilter(bucket) GROUP BY bucket ORDER BY bucket",
                    "format": "time_series",
                    "intervalMs": 3600000,
                    "maxDataPoints": 500,
                }
            ],
        }
        result = request_json(f"{GRAFANA_URL}/api/ds/query", method="POST", body=query, auth=True)
        frames = result["results"]["A"].get("frames", [])
        points = len(frames[0]["data"]["values"][0]) if frames else 0
        checks.append(Check("Grafana Timescale panel query", points > 0, f"{points} points"))
    except Exception as exc:
        checks.append(Check("Grafana API/query", False, str(exc)))
    return checks


def check_prometheus_targets() -> list[Check]:
    checks: list[Check] = []
    try:
        payload = request_json(f"{PROMETHEUS_URL}/api/v1/targets")
        targets = payload["data"]["activeTargets"]
        health_by_job = {target["labels"].get("job"): target["health"] for target in targets}
        for job in ["prometheus", "kafka", "timescaledb"]:
            health = health_by_job.get(job, "missing")
            checks.append(Check(f"Prometheus target {job}", health == "up", health))
    except Exception as exc:
        checks.append(Check("Prometheus targets", False, str(exc)))
    return checks


def check_prometheus_metrics() -> list[Check]:
    checks: list[Check] = []
    queries = {
        "Prometheus scrape count": "count(up)",
        "Prometheus up targets": "sum(up)",
        "Kafka exporter samples": "count({job=\"kafka\"})",
        "Timescale exporter samples": "count({job=\"timescaledb\"})",
    }
    for name, query in queries.items():
        try:
            payload = request_json(f"{PROMETHEUS_URL}/api/v1/query?{urlencode({'query': query})}")
            result = payload["data"].get("result", [])
            value = float(result[0]["value"][1]) if result else 0.0
            checks.append(Check(name, value > 0, f"{query} -> {value:g}"))
        except Exception as exc:
            checks.append(Check(name, False, str(exc)))
    return checks


def main() -> int:
    all_checks: list[Check] = []
    for _ in range(12):
        all_checks = (
            check_http()
            + check_timescale()
            + check_grafana_queries()
            + check_prometheus_targets()
            + check_prometheus_metrics()
        )
        if all(check.ok for check in all_checks):
            break
        time.sleep(3)

    for check in all_checks:
        status = "PASS" if check.ok else "FAIL"
        print(f"[{status}] {check.name}: {check.details}")

    return 0 if all(check.ok for check in all_checks) else 1


if __name__ == "__main__":
    sys.exit(main())
