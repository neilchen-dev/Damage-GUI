"""质心对齐消融测试：移动高斯场上 Aligned RBF vs Raw RBF。

构造"工况变化 → 图案只发生平移"的合成数据：
    D(x, y; h) = exp(-((x - h*Δ)^2 + y^2) / 2σ²)

预期：
- Raw RBF（不对齐）在工况间逐像素插值 → 图案淡化/重影，误差大；
- Centroid-Aligned RBF 恢复正确的移动图案，误差接近 0。

同一套实验既是单元测试，也是质心对齐设计的消融验证与 README 展示案例。
矩阵尺寸取 256×256（像素约 1.85 m），保证移动图案始终位于 ROI 内。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.model.rbf import RBFDamageField

SHAPE = (256, 256)
# 基准中心偏左 15 m，h 每增加 1 图案右移 10 px（约 18.5 m），
# h ∈ {0,1,2} 时图案中心从 -15 m 移动到 +22 m，始终位于 ROI x∈[-30,30] 内
PIXEL_SHIFT_PER_H = 10.0
SIGMA = 4.0
BASE_CENTER_OFFSET_PX = -8.1  # ≈ -15 m
ROI_MASK = roi_mask_for_shape(SHAPE)


def moving_gaussian(h: float) -> np.ndarray:
    """图案仅随 h 平移的高斯毁伤场。"""
    rows, cols = np.meshgrid(
        np.arange(SHAPE[0], dtype=float), np.arange(SHAPE[1], dtype=float), indexing="ij"
    )
    center_col = (SHAPE[1] - 1) / 2.0 + BASE_CENTER_OFFSET_PX + h * PIXEL_SHIFT_PER_H
    dc = cols - center_col
    dr = rows - (SHAPE[0] - 1) / 2.0
    return np.exp(-(dr * dr + dc * dc) / (2.0 * SIGMA * SIGMA)).astype(np.float32)


def build_training_data():
    """3×2×2 工况网格（h, v, deg），图案只随 h 平移。"""
    conditions = []
    matrices = []
    for h in range(3):
        for v in (0.0, 1.0):
            for deg in (0.0, 1.0):
                conditions.append([float(h), v, deg])
                matrices.append(moving_gaussian(float(h)))
    return np.array(conditions, dtype=np.float64), np.stack(matrices)


def fit_model(align: bool) -> RBFDamageField:
    conditions, matrices = build_training_data()
    model = RBFDamageField(
        kernel=CONFIG.rbf_kernel,
        smoothing=CONFIG.rbf_smoothing,
        target_shape=SHAPE,
        align=align,
    )
    model.fit(conditions, matrices)
    return model


def roi_rmse(prediction: np.ndarray, truth: np.ndarray) -> float:
    """ROI 内的 RMSE（ROI 外预测恒为 0，不属于模型评价范围）。"""
    diff = (prediction - truth)[ROI_MASK]
    return float(np.sqrt(np.mean(diff ** 2)))


class CentroidAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.aligned = fit_model(align=True)
        cls.raw = fit_model(align=False)

    def test_aligned_model_recovers_moving_pattern(self) -> None:
        """对齐模型在训练点之间的工况上恢复正确的移动图案。"""
        condition = Condition(h=0.5, v=0.5, deg=0.5)
        truth = moving_gaussian(0.5)
        prediction = self.aligned.predict_matrix(condition)
        rmse = roi_rmse(prediction, truth)
        self.assertLess(rmse, 0.05, f"对齐模型误差过大: RMSE={rmse:.4f}")

    def test_raw_model_suffers_ghosting(self) -> None:
        """不对齐模型在图案移动处出现重影/淡化，误差显著更大。"""
        condition = Condition(h=0.5, v=0.5, deg=0.5)
        truth = moving_gaussian(0.5)
        prediction = self.raw.predict_matrix(condition)
        rmse = roi_rmse(prediction, truth)
        self.assertGreater(rmse, 0.05, f"Raw 模型误差应当显著: RMSE={rmse:.4f}")

    def test_alignment_is_strictly_better_on_moving_patterns(self) -> None:
        condition = Condition(h=0.5, v=0.5, deg=0.5)
        truth = moving_gaussian(0.5)
        aligned_rmse = roi_rmse(self.aligned.predict_matrix(condition), truth)
        raw_rmse = roi_rmse(self.raw.predict_matrix(condition), truth)
        self.assertLess(aligned_rmse, raw_rmse * 0.5)


if __name__ == "__main__":
    unittest.main()
