"""工况空间的毁伤矩阵 RBF 插值场（支持质心对齐）。

对齐相关的公共工具同时供 POD-RBF 降阶模型复用。
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import center_of_mass as ndi_center_of_mass
from scipy.ndimage import shift as ndi_shift

from damage_gui.config import CONFIG, Config
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.errors import ModelFitError


def make_rbf_interpolator(
    normalized: np.ndarray,
    values: np.ndarray,
    kernel: str,
    smoothing: float,
    epsilon: float | None,
    role: str,
) -> RBFInterpolator:
    """构造带数值防护的 RBF 插值器（RBF 与 POD-RBF 共用）。

    精确插值（smoothing=0）下，归一化工况存在重复行时方程组必然奇异，
    提前给出可读错误而不是让求解器在内部崩溃；
    smoothing>0 时 scipy 走正则化最小二乘，重复工况合法，不做拦截。
    求解奇异/病态（如工况近似共线）统一转为 ModelFitError。
    epsilon 为 None 时不向 scipy 传参，保持默认启发式行为。
    """
    if (
        smoothing == 0.0
        and np.unique(normalized, axis=0).shape[0] < normalized.shape[0]
    ):
        raise ModelFitError(
            f"{role}失败：训练工况存在重复点，精确插值（smoothing=0）"
            "在重复工况下无解；请去重或将 smoothing 设为大于 0 的值"
        )
    kwargs: dict = {"kernel": kernel, "smoothing": smoothing}
    if epsilon is not None:
        kwargs["epsilon"] = epsilon
    try:
        return RBFInterpolator(normalized, values, **kwargs)
    except (np.linalg.LinAlgError, ValueError) as exc:
        raise ModelFitError(
            f"{role}失败：RBF 方程组奇异或病态（{exc}）。"
            "常见原因：训练工况共线/共面，或精确插值数值不稳定；"
            "可将 smoothing 设为略大于 0 的值重试"
        ) from exc


def compute_alignment_window(
    target_shape: tuple[int, int],
    margin: int,
    config: Config | None = None,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """插值窗口 = ROI 外包框向外扩 margin，保证对齐后的图案不越界。"""
    roi = roi_mask_for_shape(target_shape, config)
    rows = np.flatnonzero(roi.any(axis=1))
    cols = np.flatnonzero(roi.any(axis=0))
    window_rows = (
        max(0, int(rows[0]) - margin),
        min(target_shape[0], int(rows[-1]) + margin + 1),
    )
    window_cols = (
        max(0, int(cols[0]) - margin),
        min(target_shape[1], int(cols[-1]) + margin + 1),
    )
    return window_rows, window_cols


def matrix_centroid(matrix: np.ndarray, center: tuple[float, float]) -> tuple[float, float]:
    """强度加权质心；近零场回落到矩阵中心。"""
    if float(np.asarray(matrix).sum()) <= 1e-6:
        return center
    cy, cx = ndi_center_of_mass(matrix)
    return float(cy), float(cx)


def build_aligned_shapes(
    matrices: np.ndarray,
    window_rows: tuple[int, int],
    window_cols: tuple[int, int],
    align: bool,
    center: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """提取各训练矩阵的质心与（可选平移到质心居中的）窗口形状。

    返回:
        centroids: (n, 2) 各矩阵质心 (cy, cx)
        shapes: (n, window_pixels) 窗口内的形状（align=True 时已居中对齐）
    """
    r0, r1 = window_rows
    c0, c1 = window_cols
    center_r, center_c = center
    count = len(matrices)
    centroids = np.zeros((count, 2), dtype=np.float64)
    shapes = np.zeros((count, (r1 - r0) * (c1 - c0)), dtype=np.float64)

    for i, matrix in enumerate(matrices):
        cy, cx = matrix_centroid(matrix, center)
        centroids[i] = (cy, cx)
        if align:
            aligned = ndi_shift(
                matrix,
                (center_r - cy, center_c - cx),
                order=1,
                mode="constant",
                cval=0.0,
            )
        else:
            aligned = matrix
        shapes[i] = aligned[r0:r1, c0:c1].ravel()
    return centroids, shapes


class RBFDamageField:
    """工况空间的毁伤矩阵 RBF 插值场（支持质心对齐）。

    align=False：把每个像素的毁伤值看作工况 (h, v, deg) 的光滑函数直接插值。
    图案随工况平移时会产生"重影"（插值结果是新旧位置两个变淡的影子）。

    align=True：先把每幅训练矩阵平移到质心居中的标准位置，对"对齐后的形状"
    做逐像素插值；质心坐标作为工况的函数单独插值。预测时先插值出形状，
    再平移到插值出的质心位置——图案的移动被显式建模，消除重影。
    """

    def __init__(
        self,
        kernel: str,
        smoothing: float,
        target_shape: tuple[int, int],
        align: bool = True,
        config: Config | None = None,
        epsilon: float | None = None,
    ):
        self.kernel = kernel
        self.smoothing = smoothing
        self.epsilon = epsilon
        self.target_shape = target_shape
        self.align = align
        self.config = config or CONFIG
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None
        self.window_rows: tuple[int, int] | None = None
        self.window_cols: tuple[int, int] | None = None
        self.shape_interpolator: RBFInterpolator | None = None
        self.centroid_interpolator: RBFInterpolator | None = None

    @property
    def model_name(self) -> str:
        return "RBF"

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

        normalized = self._normalize(conditions)
        epsilon = getattr(self, "epsilon", None)  # 兼容旧版 joblib 模型
        self.shape_interpolator = make_rbf_interpolator(
            normalized, shapes, self.kernel, self.smoothing, epsilon, "形状插值"
        )
        if self.align:
            self.centroid_interpolator = make_rbf_interpolator(
                normalized, centroids, self.kernel, self.smoothing, epsilon, "质心插值"
            )

    def _reconstruct_window(self, query: np.ndarray) -> np.ndarray:
        """从形状插值器输出恢复窗口场（RBF 直接输出窗口像素）。"""
        return self.shape_interpolator(query)[0]

    def predict_matrix(self, condition: Condition) -> np.ndarray:
        if self.shape_interpolator is None:
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
