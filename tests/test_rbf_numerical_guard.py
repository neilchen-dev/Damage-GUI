"""RBF 数值防护测试：重复工况检测、奇异方程组包装与 epsilon 参数生效。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition
from damage_gui.errors import ModelFitError
from damage_gui.model.pod import PODRBFDamageField
from damage_gui.model.rbf import RBFDamageField


def gaussian_field(shape=(32, 32), amplitude=1.0):
    rows, cols = np.meshgrid(
        np.arange(shape[0], dtype=float), np.arange(shape[1], dtype=float), indexing="ij"
    )
    dr = rows - (shape[0] - 1) / 2.0
    dc = cols - (shape[1] - 1) / 2.0
    return (amplitude * np.exp(-(dr * dr + dc * dc) / 18.0)).astype(np.float32)


def make_matrices(amplitudes, shape=(32, 32)):
    return np.array([gaussian_field(shape, a) for a in amplitudes], dtype=np.float32)


class NumericalGuardTests(unittest.TestCase):
    def test_duplicate_conditions_raise_typed_error(self) -> None:
        """重复工况 + 精确插值（smoothing=0）→ ModelFitError 并给出可读提示。"""
        conditions = np.array(
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 1.0],
             [2.0, 1.0, 0.0], [3.0, 1.0, 1.0]],
            dtype=np.float64,
        )
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=0.0, target_shape=(32, 32)
        )
        with self.assertRaises(ModelFitError) as ctx:
            model.fit(conditions, make_matrices([0.3, 0.4, 0.5, 0.6, 0.7]))
        self.assertIn("重复", str(ctx.exception))

    def test_duplicate_conditions_with_smoothing_fit_ok(self) -> None:
        """smoothing>0 时重复工况退化为最小二乘，应可正常训练。"""
        conditions = np.array(
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 1.0],
             [2.0, 1.0, 0.0], [3.0, 1.0, 1.0]],
            dtype=np.float64,
        )
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=1e-3, target_shape=(32, 32)
        )
        model.fit(conditions, make_matrices([0.3, 0.4, 0.5, 0.6, 0.7]))
        prediction = model.predict_matrix(Condition(1.5, 0.5, 0.5))
        self.assertGreaterEqual(float(prediction.min()), 0.0)
        self.assertLessEqual(float(prediction.max()), 1.0)

    def test_collinear_conditions_raise_typed_error(self) -> None:
        """工况全部共线（仅在 h 方向变化）→ 求解器奇异/病态被包装为 ModelFitError。"""
        conditions = np.array(
            [[float(i), 0.0, 0.0] for i in range(5)], dtype=np.float64
        )
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=0.0, target_shape=(32, 32)
        )
        with self.assertRaises(ModelFitError):
            model.fit(conditions, make_matrices([0.3, 0.4, 0.5, 0.6, 0.7]))

    def test_pod_duplicate_conditions_raise_typed_error(self) -> None:
        """POD-RBF 的模态系数插值同样受防护。"""
        conditions = np.array(
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 1.0],
             [2.0, 1.0, 0.0], [3.0, 1.0, 1.0]],
            dtype=np.float64,
        )
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=0.0, target_shape=(32, 32),
            n_components=3,
        )
        with self.assertRaises(ModelFitError):
            model.fit(conditions, make_matrices([0.3, 0.4, 0.5, 0.6, 0.7]))

    def test_epsilon_parameter_is_live(self) -> None:
        """显式传入的 epsilon 对 multiquadric 核的预测结果产生实际影响。"""
        conditions = np.array(
            [[float(i), float(i % 2), float((i // 2) % 2)] for i in range(8)],
            dtype=np.float64,
        )
        matrices = make_matrices([0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65])

        def predict_with(epsilon: float | None) -> np.ndarray:
            model = RBFDamageField(
                kernel="multiquadric", smoothing=0.0, target_shape=(32, 32),
                epsilon=epsilon,
            )
            model.fit(conditions, matrices)
            return model.predict_matrix(Condition(3.5, 0.4, 0.2))

        pred_a = predict_with(0.5)
        pred_b = predict_with(5.0)
        self.assertFalse(np.allclose(pred_a, pred_b, atol=1e-6))


if __name__ == "__main__":
    unittest.main()
