"""POD-RBF 降阶模型测试：模态重构、值域与解释方差。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.model.pod import PODRBFDamageField

SHAPE = (64, 64)


def amplitude_field(amplitude: float) -> np.ndarray:
    rows, cols = np.meshgrid(
        np.arange(SHAPE[0], dtype=float), np.arange(SHAPE[1], dtype=float), indexing="ij"
    )
    dr = rows - 31.5
    dc = cols - 31.5
    return (
        amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * 5.0 * 5.0))
    ).astype(np.float32)


def make_training_set(n=8):
    # v/deg 取 0/1 交错，保证工况在三个维度都有变化（避免 RBF 秩亏）
    conditions = np.array(
        [[float(i), float(i % 2), float((i // 2) % 2)] for i in range(n)],
        dtype=np.float64,
    )
    matrices = np.stack([amplitude_field(0.2 + 0.1 * i) for i in range(n)])
    return conditions, matrices


class PODRBFTests(unittest.TestCase):
    def test_pod_rbf_recovers_training_points(self) -> None:
        conditions, matrices = make_training_set()
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel,
            smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE,
            align=True,
            n_components=5,
        )
        model.fit(conditions, matrices)
        # 幅值变化是秩 1 结构，少数模态即可完整重构
        self.assertAlmostEqual(model.explained_variance, 1.0, places=6)
        roi = roi_mask_for_shape(SHAPE)
        for i in range(len(conditions)):
            prediction = model.predict_matrix(Condition(*conditions[i]))
            np.testing.assert_allclose(
                prediction[roi], matrices[i][roi], atol=5e-3,
                err_msg=f"训练点 {i} 未被 POD-RBF 恢复",
            )

    def test_prediction_range_0_1(self) -> None:
        conditions, matrices = make_training_set()
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE, align=True, n_components=5,
        )
        model.fit(conditions, matrices)
        prediction = model.predict_matrix(Condition(3.3, 0.0, 0.0))
        self.assertGreaterEqual(float(prediction.min()), 0.0)
        self.assertLessEqual(float(prediction.max()), 1.0)

    def test_components_clamped_to_sample_count(self) -> None:
        conditions, matrices = make_training_set(n=6)
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE, align=True, n_components=50,
        )
        model.fit(conditions, matrices)
        self.assertEqual(model.n_components_used, 6)
        self.assertLessEqual(model.explained_variance, 1.0 + 1e-9)

    def test_model_name_reflects_components(self) -> None:
        conditions, matrices = make_training_set(n=6)
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE, align=True, n_components=3,
        )
        model.fit(conditions, matrices)
        self.assertIn("K=3", model.model_name)

    def test_unfitted_predict_raises(self) -> None:
        model = PODRBFDamageField("thin_plate_spline", 0.0, SHAPE)
        with self.assertRaises(RuntimeError):
            model.predict_matrix(Condition(0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
