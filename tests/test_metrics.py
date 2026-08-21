"""Focused tests for the model evaluation metric helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.evaluation.metrics import metric_row, safe_r2


class MetricTests(unittest.TestCase):
    def test_exact_prediction_has_zero_errors(self) -> None:
        truth = np.array([0.1, 0.4, 0.8], dtype=float)
        row = metric_row("damage_gt_0.05", truth, truth, area_threshold=0.05)
        self.assertEqual(row["points"], 3)
        self.assertAlmostEqual(float(row["RMSE"]), 0.0)
        self.assertAlmostEqual(float(row["MeanRelativeError"]), 0.0)
        self.assertAlmostEqual(float(row["HybridAccuracyInTarget"]), 1.0)

    def test_safe_r2_returns_nan_for_constant_truth(self) -> None:
        self.assertTrue(np.isnan(safe_r2(np.ones(3), np.ones(3))))

    def test_hybrid_error_bounds_relative_error(self) -> None:
        # true=0.06 边缘点：绝对误差 0.05 → 混合误差 = 0.05/0.25 = 0.2（封顶）
        truth = np.array([0.06], dtype=float)
        pred = np.array([0.11], dtype=float)
        row = metric_row("damage_gt_0.05", truth, pred, area_threshold=0.05)
        self.assertAlmostEqual(float(row["P95HybridError"]), 0.2, places=6)

    def test_empty_input_returns_nan_metrics(self) -> None:
        row = metric_row("overall", np.array([]), np.array([]), area_threshold=0.01)
        self.assertEqual(row["points"], 0)
        self.assertTrue(np.isnan(float(row["RMSE"])))


if __name__ == "__main__":
    unittest.main()
