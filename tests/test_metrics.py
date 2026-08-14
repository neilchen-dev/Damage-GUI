"""Focused tests for the model evaluation metric helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.app import metric_row, safe_r2


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


if __name__ == "__main__":
    unittest.main()
