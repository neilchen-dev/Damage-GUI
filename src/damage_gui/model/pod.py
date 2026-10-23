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

from damage_gui.config import CONFIG, Config
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.model.rbf import (
    build_aligned_shapes,
    compute_alignment_window,
    make_rbf_interpolator,
)


class _PODBasis:
    """POD / PCA 的轻量、确定性全 SVD 实现（替代 sklearn.decomposition.PCA）。

    仅实现本项目所需的子集：

    - ``fit_transform(X) -> (n_samples, k)``
    - ``inverse_transform(Y) -> (n_samples, n_features)``
    - ``explained_variance_ratio_``（长度 ``k`` 的 np.ndarray）

    设计动机
    --------
    - sklearn PCA 在 ``n_components < 0.8 * min(X.shape)`` 时切换到
      ``randomized`` SVD，跨 sklearn 版本输出不稳定，与本项目
      "可追溯交付、跨版本一致数值"的承诺矛盾。
    - 核心算法层不应依赖第三方 ML 全栈；本类 + ``numpy.linalg.svd``
      已经足够。
    - PyInstaller 桌面分发少 ~35MB（移除 scikit-learn 依赖）。

    实现要点
    --------
    - 一律走 ``np.linalg.svd(..., full_matrices=False)``（LAPACK gesdd）。
    - 复现 sklearn 1.x ``svd_flip`` 的符号约定：取变换结果每列
      ``abs`` 最大元素的符号作为基向量翻转方向，保证跨 numpy / LAPACK
      版本基向量符号一致。
    """

    def __init__(self, n_components: int) -> None:
        self.n_components = int(n_components)
        self.mean_: np.ndarray | None = None
        self.components_: np.ndarray | None = None  # (k, n_features)
        self.explained_variance_ratio_: np.ndarray | None = None  # (k,)

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        if X.ndim != 2:
            raise ValueError("POD 基底要求 2-D 输入 (n_samples, n_features)")
        n_samples = X.shape[0]
        if n_samples < 1:
            raise ValueError("POD 基底需要至少 1 个样本")
        self.mean_ = X.mean(axis=0)
        Xc = X - self.mean_
        _, S, Vt = np.linalg.svd(Xc, full_matrices=False)
        k = min(self.n_components, S.size)
        Y = Xc @ Vt[:k].T  # (n_samples, k) —— 训练系数未做符号翻转
        # 与 sklearn svd_flip 等价的符号约定：每列取 |Y| 最大元素的符号
        # 翻转该列；保证基向量与逆变换在跨 numpy/LAPACK 版本下符号一致。
        if k > 0:
            max_abs_idx = np.argmax(np.abs(Y), axis=0)
            signs = np.sign(Y[max_abs_idx, np.arange(k)])
            signs = np.where(signs == 0, 1.0, signs)
            self.components_ = Vt[:k] * signs[:, None]
            Y = Y * signs
        else:
            self.components_ = np.zeros((0, X.shape[1]), dtype=np.float64)
        ev_full = (S ** 2) / max(1, n_samples - 1)
        total = float(ev_full.sum())
        self.explained_variance_ratio_ = (ev_full / total)[:k]
        return Y

    def inverse_transform(self, Y: np.ndarray) -> np.ndarray:
        if self.mean_ is None or self.components_ is None:
            raise RuntimeError("POD 基底尚未 fit")
        Y = np.asarray(Y, dtype=np.float64)
        return Y @ self.components_ + self.mean_


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
        epsilon: float | None = None,
    ):
        self.kernel = kernel
        self.smoothing = smoothing
        self.epsilon = epsilon
        self.target_shape = target_shape
        self.align = align
        self.n_components = int(n_components)
        self.config = config or CONFIG
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None
        self.window_rows: tuple[int, int] | None = None
        self.window_cols: tuple[int, int] | None = None
        self.pod: _PODBasis | None = None  # 历史命名 pca 已被去除（避免与 sklearn 混用）
        self.coeff_interpolator: RBFInterpolator | None = None
        self.centroid_interpolator: RBFInterpolator | None = None
        self.explained_variance: float = 0.0
        self.n_components_used: int = 0

    def __setstate__(self, state: dict) -> None:
        """兼容 v2.2 旧版 joblib 模型：sklearn PCA 时代属性名为 ``pca``。

        旧模型 unpickle 时状态字典里只有 ``pca``（sklearn.decomposition.PCA
        实例，反序列化需要 ``damage-gui[legacy]``）。sklearn PCA 的
        ``inverse_transform`` 与 ``_PODBasis`` 接口一致（``Y @ components_ +
        mean_``），直接改名接管即可，数值不变。
        """
        if "pod" not in state and "pca" in state:
            state["pod"] = state.pop("pca")
        self.__dict__.update(state)

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

        # POD 分量数受样本数与窗口像素数双重约束
        n_comp = min(
            self.n_components,
            shapes.shape[0],
            shapes.shape[1],
        )
        n_comp = max(1, n_comp)
        self.pod = _PODBasis(n_components=n_comp)
        coefficients = self.pod.fit_transform(shapes)
        self.explained_variance = float(np.sum(self.pod.explained_variance_ratio_))
        self.n_components_used = int(n_comp)

        normalized = self._normalize(conditions)
        epsilon = getattr(self, "epsilon", None)  # 兼容旧版 joblib 模型
        self.coeff_interpolator = make_rbf_interpolator(
            normalized, coefficients, self.kernel, self.smoothing, epsilon,
            "模态系数插值",
        )
        if self.align:
            self.centroid_interpolator = make_rbf_interpolator(
                normalized, centroids, self.kernel, self.smoothing, epsilon,
                "质心插值",
            )

    def _reconstruct_window(self, query: np.ndarray) -> np.ndarray:
        """插值模态系数并做逆 POD 变换恢复窗口场。"""
        coefficients = self.coeff_interpolator(query)
        return self.pod.inverse_transform(coefficients.reshape(1, -1))[0]

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
