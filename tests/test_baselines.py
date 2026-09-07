"""M3.2 基线模型测试：最近邻 + 逐像素线性插值。"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from damage_gui.config import CONFIG  # noqa: E402
from damage_gui.data.loader import Condition  # noqa: E402
from damage_gui.data.preprocessing import roi_mask_for_shape  # noqa: E402
from damage_gui.errors import ModelFitError  # noqa: E402
from damage_gui.experiments.baselines import (  # noqa: E402
    LinearInterpField,
    NearestNeighborField,
)
from damage_gui.experiments.runner import baseline_specs, run_suite  # noqa: E402
from damage_gui.model.bundle import build_model  # noqa: E402
from synthetic_data import make_service, make_synthetic_dataset  # noqa: E402

SHAPE = (16, 16)


def small_config():
    return dataclasses.replace(CONFIG, target_shape=SHAPE)


def affine_matrices(conditions: np.ndarray) -> np.ndarray:
    """像素值 = 工况的仿射函数（线性插值理论上可精确复原）。"""
    matrices = np.zeros((len(conditions), *SHAPE), dtype=np.float32)
    pixel = np.linspace(0.0, 0.2, SHAPE[0] * SHAPE[1]).reshape(SHAPE)
    for i, (h, v, deg) in enumerate(conditions):
        matrices[i] = 0.1 + pixel + 0.001 * h + 0.0001 * v + 0.0005 * deg
    return np.clip(matrices, 0.0, 1.0)


class NearestNeighborFieldTests(unittest.TestCase):
    def test_predict_returns_nearest_training_matrix(self) -> None:
        config = small_config()
        roi = roi_mask_for_shape(SHAPE, config)
        conditions = np.array(
            [[0.0, 100.0, 10.0], [1.0, 200.0, 20.0], [2.0, 300.0, 30.0], [3.0, 400.0, 40.0]]
        )
        matrices = np.stack(
            [np.full(SHAPE, 0.1 * (i + 1), dtype=np.float32) for i in range(4)]
        )
        model = NearestNeighborField(SHAPE, config=config)
        model.fit(conditions, matrices)

        for index, (h, v, deg) in enumerate(conditions):
            expected = np.clip(matrices[index], 0.0, 1.0)
            expected[~roi] = 0.0
            pred = model.predict_matrix(Condition(h, v, deg))
            np.testing.assert_array_equal(pred, expected.astype(np.float32))

        near_last = model.predict_matrix(Condition(2.9, 380.0, 38.0))
        np.testing.assert_array_equal(
            near_last[roi], np.full(int(roi.sum()), 0.4, dtype=np.float32)
        )

    def test_build_model_creates_nn(self) -> None:
        self.assertIsInstance(build_model("nn", small_config()), NearestNeighborField)


class LinearInterpFieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = small_config()
        self.roi = roi_mask_for_shape(SHAPE, self.config)
        self.conditions = np.array(
            [
                [0.0, 100.0, 10.0],
                [3.0, 100.0, 10.0],
                [0.0, 400.0, 10.0],
                [0.0, 100.0, 80.0],
                [3.0, 400.0, 80.0],
            ]
        )
        self.matrices = affine_matrices(self.conditions)

    def test_reproduces_affine_field_inside_hull(self) -> None:
        model = LinearInterpField(SHAPE, config=self.config)
        model.fit(self.conditions, self.matrices)

        mid = self.conditions.mean(axis=0)  # 训练点均值必在凸包内
        pred = model.predict_matrix(Condition(*mid))
        expected = 0.1 + 0.001 * mid[0] + 0.0001 * mid[1] + 0.0005 * mid[2]
        pixel = np.linspace(0.0, 0.2, SHAPE[0] * SHAPE[1]).reshape(SHAPE)
        np.testing.assert_allclose(
            pred[self.roi], (expected + pixel)[self.roi], atol=1e-6
        )
        np.testing.assert_array_equal(pred[~self.roi], 0.0)
        self.assertEqual(model.extrapolation_fraction, 0.0)

    def test_outside_hull_falls_back_to_nearest_and_counts(self) -> None:
        model = LinearInterpField(SHAPE, config=self.config)
        model.fit(self.conditions, self.matrices)

        pred = model.predict_matrix(Condition(50.0, 999.0, 89.0))
        self.assertEqual(model.total_queries, 1)
        self.assertEqual(model.extrapolation_queries, 1)
        self.assertAlmostEqual(model.extrapolation_fraction, 1.0)
        np.testing.assert_allclose(
            pred[self.roi], self.matrices[-1][self.roi], atol=1e-6
        )

    def test_collinear_conditions_raise_readable_error(self) -> None:
        collinear = np.array(
            [[float(i), 100.0, 10.0] for i in range(5)]
        )
        model = LinearInterpField(SHAPE, config=self.config)
        with self.assertRaises(ModelFitError) as ctx:
            model.fit(collinear, affine_matrices(collinear))
        self.assertIn("线性插值", str(ctx.exception))

    def test_build_model_creates_linear(self) -> None:
        self.assertIsInstance(
            build_model("linear", small_config()), LinearInterpField
        )


class BaselineSuiteTests(unittest.TestCase):
    def test_baseline_suite_runs_on_synthetic_data(self) -> None:
        tmp, _data_dir = make_synthetic_dataset()
        try:
            service = make_service(Path(tmp.name))
            results = run_suite(service, "F", baseline_specs(), suite="baseline")
            self.assertEqual([r.experiment for r in results],
                             ["baseline_nn", "baseline_linear"])
            self.assertEqual([r.status for r in results], ["ok", "ok"])
            linear = results[1]
            self.assertIsNotNone(linear.extrapolation_fraction)
            self.assertGreaterEqual(linear.extrapolation_fraction, 0.0)
            self.assertLessEqual(linear.extrapolation_fraction, 1.0)
            self.assertIn("mean_relative_error", linear.metrics)
            self.assertIsNone(results[0].extrapolation_fraction)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
