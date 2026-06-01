from __future__ import annotations

import math
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from anomaly_detection import AnomalyConfig, rolling_median_mad_anomalies
from eval_anomaly_detection import evaluate, event_detection_metrics
from inject_anomalies import inject_anomalies
from train_prophet import choose_cutoffs, evaluate_group, horizon_steps, wape

sys.path.insert(0, str(ROOT / "scripts"))
from compare_anomaly_thresholds import best_operating_point, build_table, default_thresholds
from replay_profile_to_kafka import replay_messages


class MLPipelineTests(unittest.TestCase):
    def test_wape(self) -> None:
        self.assertAlmostEqual(wape([10, 20, 30], [8, 22, 33]), 7 / 60)

    def test_30m_horizon_and_rolling_origin(self) -> None:
        self.assertEqual(horizon_steps(24, 30), 48)
        cutoffs = choose_cutoffs(n=1008, start=48, horizon=48, folds=20)
        self.assertEqual(len(cutoffs), 20)
        self.assertEqual(cutoffs[0], 48)
        self.assertEqual(cutoffs[-1], 960)

    def test_benchmark_main_story_has_no_clustering_dependency(self) -> None:
        benchmark_source = (ROOT / "ml" / "benchmark_ml.py").read_text(encoding="utf-8")
        self.assertNotIn("clustering", benchmark_source)

    def test_forecast_fallback_runs(self) -> None:
        start = datetime(2023, 1, 1)
        series = []
        for idx in range(24 * 10):
            ts = start + timedelta(hours=idx)
            series.append((ts, 1.0 + (ts.hour / 24)))
        forecasts, metrics = evaluate_group("demo", series, model="seasonal_naive", horizon_hours_value=24, folds=2)
        self.assertGreater(len(forecasts), 0)
        self.assertEqual(metrics["model_type"], "seasonal_naive_fallback")
        self.assertFalse(math.isnan(metrics["wape_horizon"]))

    def test_injection_marks_ground_truth(self) -> None:
        start = datetime(2023, 1, 1)
        rows = []
        for idx in range(24 * 21):
            rows.append(
                {
                    "time": (start + timedelta(hours=idx)).isoformat(sep=" "),
                    "meter_id": "M1",
                    "kwh": "1.00000000",
                    "is_anomaly": "false",
                    "source": "test",
                }
            )
        report = inject_anomalies(
            rows,
            group_by="meter_id",
            seed=7,
            point_per_group=1,
            segment_steps=2,
            drift_steps=4,
            spike_k=8.0,
            drift_percent=0.5,
        )
        self.assertGreater(report["total_ground_truth_rows"], 0)
        self.assertTrue(any(row["is_anomaly"] == "true" for row in rows))
        self.assertTrue(any(row.get("anomaly_type") for row in rows if row["is_anomaly"] == "true"))

    def test_mad_detector_catches_spike(self) -> None:
        values = [1.0, 1.1, 0.9, 1.0, 1.1, 0.9, 1.0, 8.0]
        flags = rolling_median_mad_anomalies(values, AnomalyConfig(window=4, mad_multiplier=3.5))
        self.assertTrue(flags[-1])

    def test_event_level_scoring_requires_confirmed_non_point_flags(self) -> None:
        truth = [False, True, True, True, True, True, True, False]
        weak_pred = [False, True, False, False, False, False, False, False]
        strong_pred = [False, True, True, True, True, True, False, False]
        types = ["", "contextual_day_night_swap", "contextual_day_night_swap", "contextual_day_night_swap", "contextual_day_night_swap", "contextual_day_night_swap", "contextual_day_night_swap", ""]
        weak = event_detection_metrics(truth, weak_pred, types, tolerance_steps=0, event_min_flags=5, event_min_consecutive=1)
        strong = event_detection_metrics(truth, strong_pred, types, tolerance_steps=0, event_min_flags=5, event_min_consecutive=1)
        self.assertEqual(weak["fn"], 1)
        self.assertEqual(strong["tp"], 1)

    def test_forecast_residual_eval_catches_spike_and_latency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            injected = root / "tiny_injected.csv"
            forecasts = root / "tiny_forecasts.csv"
            start = datetime(2023, 1, 1)
            with injected.open("w", encoding="utf-8") as handle:
                handle.write("time,meter_id,kwh,is_anomaly,source,anomaly_type\n")
                for idx in range(12):
                    value = 10.0 if idx == 8 else 1.0
                    truth = "true" if idx == 8 else "false"
                    kind = "point_spike" if idx == 8 else ""
                    ts = start + timedelta(minutes=30 * idx)
                    handle.write(f"{ts.isoformat(sep=' ')},M1,{value:.8f},{truth},demo,{kind}\n")
            with forecasts.open("w", encoding="utf-8") as handle:
                handle.write("group_key,fold,horizon_step,time,actual,forecast,model_type\n")
                for idx in range(12):
                    ts = start + timedelta(minutes=30 * idx)
                    handle.write(f"demo,1,{idx + 1},{ts.isoformat(sep=' ')},1.00000000,1.00000000,seasonal_naive\n")

            payload = evaluate(
                injected,
                group_by="source",
                window=4,
                mad_multiplier=3.0,
                min_abs_deviation=0.5,
                tolerance_steps=1,
                forecast_file=forecasts,
            )
            self.assertEqual(payload["detector"], "forecast_residual_mad")
            self.assertGreaterEqual(payload["overall"]["tp"], 1)
            self.assertIn("point_spike", payload["by_anomaly_type"])
            self.assertEqual(payload["groups"]["demo"]["avg_latency_samples"], 0)

    def test_threshold_table_exposes_operating_point(self) -> None:
        self.assertEqual(default_thresholds()[0], 0.5)
        self.assertEqual(default_thresholds()[-1], 5.0)
        table = build_table(
            [
                {
                    "mad_multiplier": 2.0,
                    "overall": {"precision": 0.8, "recall": 0.9, "f1": 0.847, "tp": 9, "fp": 2, "fn": 1, "tn": 88},
                }
            ]
        )
        self.assertIn("Seuil MAD", table)
        self.assertIn("0.9000", table)

        best = best_operating_point(
            [
                {
                    "mad_multiplier": 1.0,
                    "overall": {"precision": 0.9, "recall": 1.0, "f1": 0.947},
                },
                {
                    "mad_multiplier": 2.0,
                    "overall": {"precision": 0.97, "recall": 0.8, "f1": 0.878},
                },
            ],
            min_precision=0.95,
        )
        self.assertEqual(best["mad_multiplier"], 2.0)

    def test_live_replay_messages_keep_source_and_inject_anomaly(self) -> None:
        rows = [
            {"time": "2023-01-01 00:00:00", "meter_id": "M1", "kwh": "1.0", "is_anomaly": "false", "source": "london"},
            {"time": "2023-01-01 01:00:00", "meter_id": "M1", "kwh": "2.0", "is_anomaly": "false", "source": "london"},
        ]
        start = datetime(2026, 1, 1)
        messages = list(replay_messages(rows, start_time=start, cadence_seconds=60, anomaly_every=1, anomaly_factor=2.5))
        self.assertEqual(messages[0]["source"], "london")
        self.assertEqual(messages[1]["kwh"], 5.0)
        self.assertTrue(messages[1]["is_anomaly"])


if __name__ == "__main__":
    unittest.main()
