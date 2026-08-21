"""空间场专用指标测试：质心误差 / 峰值误差 / IoU / Dice。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.evaluation.metrics import field_centroid, spatial_metrics


def gaussian_field(shape=(64, 64), center=(32.0, 32.0), sigma=4.0, amplitude=1.0):
    rows, cols = np.meshgrid(
        np.arange(shape[0], dtype=float), np.arange(shape[1], dtype=float), indexing="ij"
    )
    dr = rows - center[0]
    dc = cols - center[1]
    return amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * sigma * sigma))


class SpatialMetricTests(unittest.TestCase):
    def test_identical_fields_have_perfect_scores(self) -> None:
        field = gaussian_field()
        result = spatial_metrics(field, field, damage_threshold=0.05, pixel_size_x=1.0)
        self.assertAlmostEqual(result["CentroidError"], 0.0, places=9)
        self.assertAlmostEqual(result["PeakIntensityError"], 0.0, places=9)
        self.assertAlmostEqual(result["PeakPositionError"], 0.0, places=9)
        self.assertAlmostEqual(result["IoU"], 1.0, places=9)
        self.assertAlmostEqual(result["Dice"], 1.0, places=9)

    def test_shifted_field_reports_centroid_and_position_error(self) -> None:
        true_field = gaussian_field(center=(32.0, 32.0))
        pred_field = gaussian_field(center=(32.0, 37.0))
        result = spatial_metrics(true_field, pred_field, 0.05, pixel_size_x=2.0)
        self.assertAlmostEqual(result["CentroidError"], 10.0, places=6)
        self.assertAlmostEqual(result["PeakPositionError"], 10.0, places=6)
        self.assertLess(result["IoU"], 1.0)
        self.assertLess(result["Dice"], 1.0)
        self.assertGreater(result["IoU"], 0.0)

    def test_disjoint_damage_regions_have_zero_overlap(self) -> None:
        true_field = gaussian_field(center=(10.0, 10.0), sigma=2.0)
        pred_field = gaussian_field(center=(50.0, 50.0), sigma=2.0)
        result = spatial_metrics(true_field, pred_field, 0.05, pixel_size_x=1.0)
        self.assertAlmostEqual(result["IoU"], 0.0, places=9)
        self.assertAlmostEqual(result["Dice"], 0.0, places=9)
        self.assertTrue(np.isnan(result["CentroidError"]) or result["CentroidError"] > 0)

    def test_both_empty_damage_regions_score_full_agreement(self) -> None:
        flat = np.full((16, 16), 0.001)
        result = spatial_metrics(flat, flat, damage_threshold=0.05, pixel_size_x=1.0)
        self.assertAlmostEqual(result["IoU"], 1.0, places=9)
        self.assertAlmostEqual(result["Dice"], 1.0, places=9)

    def test_amplitude_change_reports_peak_intensity_error(self) -> None:
        true_field = gaussian_field(amplitude=1.0)
        pred_field = gaussian_field(amplitude=0.7)
        result = spatial_metrics(true_field, pred_field, 0.05, pixel_size_x=1.0)
        self.assertAlmostEqual(result["PeakIntensityError"], 0.3, places=6)
        self.assertAlmostEqual(result["CentroidError"], 0.0, places=6)

    def test_field_centroid_of_zero_field_is_none(self) -> None:
        self.assertIsNone(field_centroid(np.zeros((8, 8))))


if __name__ == "__main__":
    unittest.main()
