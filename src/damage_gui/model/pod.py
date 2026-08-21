"""POD / PCA 降阶 + RBF 模态系数插值的毁伤场代理模型。

流程：
    Damage Matrix
        ↓ 质心对齐（图案平移解耦）
    POD / PCA 降维
        ↓
    低维模态系数 a_k（K = 10~30）
        ↓ RBF 在 (h, v, deg) 工况空间插值
    预测模态系数
        ↓ 逆 POD 变换
    质心恢复 → Damage Matrix

数学形式：D(x, y) ≈ D̄(x, y) + Σ_k a_k φ_k(x, y)，
其中 φ_k 为 POD 模态，a_k 为对应工况下的模态系数。
RBF 不再逐像素预测上万维输出，只需预测 K 维模态系数。
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import shift as ndi_shift
from sklearn.decomposition import PCA

from damage_gui.config import Config, CONFIG
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.model.rbf import build_aligned_shapes, compute_alignment_window


class PODRBFDamageField:
    """质心对齐 + POD 降阶 + RBF 模态系数插值的毁伤场代理模型。

    与 RBFDamageField 接口一致（fit / predict_matrix），可直接替换使用。
    """

    def __init__(
        self,
        kernel: str,
        smoothing: float,
        target_shape: tuple[int, int],
        align: bool = True,
        n_components: int = 20,
        config: Config | None = None,
    ):
        self.kernel = kernel
        self.smoothing = smoothing
        self.target_shape = target_shape
        self.align = align
        self.n_components = int(n_components)
        self.config = config or CONFIG
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None
        self.window_rows: tuple[int, int] | None = None
        self.window_cols: tuple[int, int] | None = None
        self.pca: PCA | None = None
        self.coeff_interpolator: RBFInterpolator | None = None
        self.centroid_interpolator: RBFInterpolator | None = None
        self.explained_variance: float = 0.0
        self.n_components_used: int = 0

    @property
    def model_name(self) -> str:
        return f"POD-RBF(K={self.n_components_used})"

    @property
    def _center(self) -> tuple[float, float]:
        return ((self.target_shape[0] - 1) / 2.0, (self.target_shape[1] - 1) / 2.0)

    def _normalize(self, conditions: np.ndarray) -> np.ndarray:
        return (np.asarray(conditions, dtype=np.float64) - self.cond_lo) / self.cond_span

    def fit(self, conditions: np.ndarray, matrices: np.ndarray) -> None:
        """conditions: (n, 3)；matrices: (n, rows, cols) 完整毁伤矩阵。"""
        conditions = np.asarray(conditions, dtype=np.float64)
        lo = conditions.min(axis=0)
        hi = conditions.max(axis=0)
        self.cond_lo = lo
        self.cond_span = np.where(hi > lo, hi - lo, 1.0)
        self.window_rows, self.window_cols = compute_alignment_window(
            self.target_shape, self.config.align_window_margin, self.config
        )

        centroids, shapes = build_aligned_shapes(
            matrices, self.window_rows, self.window_cols, self.align, self._center
        )

        # PCA 分量数受样本数与窗口像素数双重约束
        n_comp = min(
            self.n_components,
            shapes.shape[0],
            shapes.shape[1],
        )
        n_comp = max(1, n_comp)
        self.pca = PCA(n_components=n_comp)
        coefficients = self.pca.fit_transform(shapes)
        self.explained_variance = float(np.sum(self.pca.explained_variance_ratio_))
        self.n_components_used = int(n_comp)

        normalized = self._normalize(conditions)
        self.coeff_interpolator = RBFInterpolator(
            normalized,
            coefficients,
            kernel=self.kernel,
            smoothing=self.smoothing,
        )
        if self.align:
            self.centroid_interpolator = RBFInterpolator(
                normalized,
                centroids,
                kernel=self.kernel,
                smoothing=self.smoothing,
            )

    def _reconstruct_window(self, query: np.ndarray) -> np.ndarray:
        """插值模态系数并做逆 POD 变换恢复窗口场。"""
        coefficients = self.coeff_interpolator(query)
        return self.pca.inverse_transform(coefficients.reshape(1, -1))[0]

    def predict_matrix(self, condition: Condition) -> np.ndarray:
        if self.coeff_interpolator is None:
            raise RuntimeError("模型尚未训练")
        query = self._normalize(condition.as_array().reshape(1, -1))

        r0, r1 = self.window_rows
        c0, c1 = self.window_cols
        window = np.clip(self._reconstruct_window(query), 0.0, 1.0)
        matrix = np.zeros(self.target_shape, dtype=np.float32)
        matrix[r0:r1, c0:c1] = window.reshape(r1 - r0, c1 - c0).astype(np.float32)

        if self.align:
            center_r, center_c = self._center
            cy, cx = self.centroid_interpolator(query)[0]
            matrix = ndi_shift(
                matrix,
                (cy - center_r, cx - center_c),
                order=1,
                mode="constant",
                cval=0.0,
            )

        config = getattr(self, "config", CONFIG)  # 兼容旧版 joblib 模型
        matrix[~roi_mask_for_shape(self.target_shape, config)] = 0.0
        return np.clip(matrix, 0.0, 1.0).astype(np.float32)
