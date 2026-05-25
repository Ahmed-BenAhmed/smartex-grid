from __future__ import annotations

import math
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from anomaly_detection import AnomalyConfig, rolling_median_mad_anomalies
from inject_anomalies import inject_anomalies
from train_prophet import evaluate_group, wape


class MLPipelineTests(unittest.TestCase):
    def test_wape(self) -> None:
        self.assertAlmostEqual(wape([10, 20, 30], [8, 22, 33]), 7 / 60)

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

    def test_mad_detector_catches_spike(self) -> None:
        values = [1.0, 1.1, 0.9, 1.0, 1.1, 0.9, 1.0, 8.0]
        flags = rolling_median_mad_anomalies(values, AnomalyConfig(window=4, mad_multiplier=3.5))
        self.assertTrue(flags[-1])


if __name__ == "__main__":
    unittest.main()
