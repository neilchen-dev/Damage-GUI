"""RBF 插值场核心行为测试：训练点恢复、值域、ROI、尺寸归一化与保存加载。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import normalize_matrix_shape, roi_mask_for_shape
from damage_gui.model.bundle import ModelBundle
from damage_gui.model.rbf import RBFDamageField


def gaussian_field(shape=(64, 64), center=(31.5, 31.5), sigma=4.0, amplitude=1.0):
    rows, cols = np.meshgrid(
        np.arange(shape[0], dtype=float), np.arange(shape[1], dtype=float), indexing="ij"
    )
    dr = rows - center[0]
    dc = cols - center[1]
    return (amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * sigma * sigma))).astype(np.float32)


def make_training_set(n=8, shape=(64, 64)):
    """中心高斯图案，幅值随条件变化；训练点应可被精确恢复。

    工况在 (h, v, deg) 三个维度都有变化（v/deg 取 0/1 交错），
    避免 RBF 单项式矩阵秩亏（全部共线时 scipy 会抛 LinAlgError）。
    """
    conditions = np.array(
        [[float(i), float(i % 2), float((i // 2) % 2)] for i in range(n)],
        dtype=np.float64,
    )
    matrices = np.zeros((n, *shape), dtype=np.float32)
    for i in range(n):
        matrices[i] = gaussian_field(shape, amplitude=0.3 + 0.1 * i)
    return conditions, matrices


class RBFModelTests(unittest.TestCase):
    def test_rbf_recovers_training_points(self) -> None:
        conditions, matrices = make_training_set()
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel,
            smoothing=CONFIG.rbf_smoothing,
            target_shape=(64, 64),
            align=True,
        )
        model.fit(conditions, matrices)
        roi = roi_mask_for_shape((64, 64))
        for i in range(len(conditions)):
            condition = Condition(*conditions[i])
            prediction = model.predict_matrix(condition)
            # 训练点上的精确插值（图案居中，质心平移量为 0）；
            # ROI 外预测恒为 0，不属于模型评价范围
            np.testing.assert_allclose(
                prediction[roi], matrices[i][roi], atol=2e-3,
                err_msg=f"训练点 {i} 未被恢复",
            )

    def test_prediction_range_0_1(self) -> None:
        conditions, matrices = make_training_set()
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=(64, 64), align=True,
        )
        model.fit(conditions, matrices)
        prediction = model.predict_matrix(Condition(3.3, 0.4, 0.2))
        self.assertGreaterEqual(float(prediction.min()), 0.0)
        self.assertLessEqual(float(prediction.max()), 1.0)

    def test_roi_outside_is_zero(self) -> None:
        conditions, matrices = make_training_set()
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=(64, 64), align=True,
        )
        model.fit(conditions, matrices)
        prediction = model.predict_matrix(Condition(2.0, 0.0, 0.0))
        roi = roi_mask_for_shape((64, 64))
        # ROI 外（如矩阵角落）预测值恒为 0
        np.testing.assert_array_equal(prediction[~roi], 0.0)

    def test_damage_matrix_resize(self) -> None:
        matrix = gaussian_field(shape=(100, 100), amplitude=0.8)
        resized = normalize_matrix_shape(matrix, (473, 473))
        self.assertEqual(resized.shape, (473, 473))
        self.assertGreaterEqual(float(resized.min()), 0.0)
        self.assertLessEqual(float(resized.max()), 1.0)
        # 缩放后峰值基本保留
        self.assertGreater(float(resized.max()), 0.6)

    def test_model_save_load_roundtrip(self) -> None:
        conditions, matrices = make_training_set(n=5)
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=(64, 64), align=True,
        )
        model.fit(conditions, matrices)
        bundle = ModelBundle(
            level="F",
            data_dir="synthetic",
            target_shape=(64, 64),
            config=CONFIG.__dict__.copy(),
            model=model,
            train_conditions=[{"h": c[0], "v": c[1], "deg": c[2]} for c in conditions],
            test_conditions=[],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.joblib"
            joblib.dump(bundle, path)
            loaded = joblib.load(path)
        self.assertIsInstance(loaded, ModelBundle)
        condition = Condition(2.0, 0.0, 0.0)
        np.testing.assert_allclose(
            loaded.model.predict_matrix(condition),
            model.predict_matrix(condition),
            atol=1e-8,
        )


if __name__ == "__main__":
    unittest.main()
