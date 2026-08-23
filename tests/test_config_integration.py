"""配置隔离测试：自定义 Config 必须贯穿坐标、ROI、平滑与指标。"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import Config, CONFIG
from damage_gui.data.preprocessing import (
    coordinate_axes,
    evaluation_fields,
    roi_mask_for_shape,
)
from damage_gui.evaluation.metrics import metric_row


class ConfigIntegrationTests(unittest.TestCase):
    def test_coordinate_axes_use_supplied_config(self) -> None:
        config = dataclasses.replace(CONFIG, coord_min=-10.0, coord_max=20.0)
        x_axis, y_axis = coordinate_axes((3, 4), config)
        self.assertEqual((float(x_axis[0]), float(x_axis[-1])), (-10.0, 20.0))
        self.assertEqual((float(y_axis[0]), float(y_axis[-1])), (-10.0, 20.0))

    def test_roi_uses_supplied_config(self) -> None:
        config = dataclasses.replace(
            CONFIG,
            coord_min=-1.0,
            coord_max=1.0,
            roi_x_min=-0.1,
            roi_x_max=0.1,
            roi_y_min=-0.1,
            roi_y_max=0.1,
        )
        mask = roi_mask_for_shape((3, 3), config)
        expected = np.zeros((3, 3), dtype=bool)
        expected[1, 1] = True
        np.testing.assert_array_equal(mask, expected)

    def test_evaluation_smoothing_uses_supplied_config(self) -> None:
        impulse = np.zeros((7, 7), dtype=np.float32)
        impulse[3, 3] = 1.0
        raw_config = dataclasses.replace(CONFIG, eval_smoothing_sigma=0.0)
        smooth_config = dataclasses.replace(CONFIG, eval_smoothing_sigma=1.0)

        raw_true, _ = evaluation_fields(impulse, impulse, raw_config)
        smooth_true, _ = evaluation_fields(impulse, impulse, smooth_config)
        np.testing.assert_array_equal(raw_true, impulse)
        self.assertLess(float(smooth_true[3, 3]), 1.0)

    def test_metric_thresholds_use_supplied_config(self) -> None:
        config = dataclasses.replace(
            CONFIG,
            relative_error_threshold=0.1,
            hybrid_error_floor=1.0,
            relative_error_target=0.2,
        )
        row = metric_row(
            "damage_gt_0.10",
            np.array([0.2]),
            np.array([0.3]),
            0.1,
            config,
        )
        self.assertAlmostEqual(float(row["MeanRelativeError"]), 0.5, places=6)
        self.assertAlmostEqual(float(row["P95HybridError"]), 0.1, places=6)
        self.assertEqual(float(row["HybridAccuracyInTarget"]), 1.0)

    def test_config_from_mapping_ignores_unknown_fields(self) -> None:
        config = Config.from_mapping({"coord_min": -9.0, "future_option": True})
        self.assertEqual(config.coord_min, -9.0)
        self.assertFalse(hasattr(config, "future_option"))


if __name__ == "__main__":
    unittest.main()
