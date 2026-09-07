"""M3.2 基线模型：最近邻与逐像素线性插值。

基线用于回答"RBF 家族相对平凡插值器到底赚了多少"。两者实现与
RBFDamageField 相同的 fit / predict_matrix 接口，可直接进入
train_bundle 与实验框架的评估管线（同一验证切分、同一双口径指标）。

数学适用性说明（诚实记录局限）：
- 最近邻：处处有定义，但预测值只能是某个训练矩阵的复制，无法反映
  工况间的连续变化；作为误差下界参照。
- 线性插值（LinearNDInterpolator）：只在训练工况的凸包内有定义，
  凸包外（外推区域）数学上无解。实现上以最近邻值回填，并把触发
  回填的预测比例记录在 ``extrapolation_fraction`` 中，报告中必须
  连同该比例一起解读；结构化留出（整层留出/角落）验证中该比例
  通常很高，线性基线在这些口径下的指标不代表其真实能力。
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import QhullError

from damage_gui.config import CONFIG, Config
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.errors import ModelFitError


class NearestNeighborField:
    """最近邻基线：预测 = 归一化工况空间中最近训练工况的矩阵复制。"""

    def __init__(
        self,
        target_shape: tuple[int, int],
        config: Config | None = None,
    ):
        self.target_shape = target_shape
        self.config = config or CONFIG
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None
        self._normalized: np.ndarray | None = None
        self._matrices: np.ndarray | None = None

    @property
    def model_name(self) -> str:
        return "NearestNeighbor"

    def _normalize(self, conditions: np.ndarray) -> np.ndarray:
        return (np.asarray(conditions, dtype=np.float64) - self.cond_lo) / self.cond_span

    def fit(self, conditions: np.ndarray, matrices: np.ndarray) -> None:
        conditions = np.asarray(conditions, dtype=np.float64)
        lo = conditions.min(axis=0)
        hi = conditions.max(axis=0)
        self.cond_lo = lo
        self.cond_span = np.where(hi > lo, hi - lo, 1.0)
        self._normalized = self._normalize(conditions)
        self._matrices = np.asarray(matrices)

    def nearest_index(self, condition: Condition) -> int:
        if self._normalized is None:
            raise RuntimeError("模型尚未训练")
        query = self._normalize(condition.as_array().reshape(1, -1))
        distances = np.linalg.norm(self._normalized - query, axis=1)
        return int(np.argmin(distances))

    def predict_matrix(self, condition: Condition) -> np.ndarray:
        index = self.nearest_index(condition)
        matrix = np.array(self._matrices[index], dtype=np.float32)
        matrix[~roi_mask_for_shape(self.target_shape, self.config)] = 0.0
        return np.clip(matrix, 0.0, 1.0).astype(np.float32)


class LinearInterpField:
    """线性基线：ROI 像素上的 LinearNDInterpolator（凸包外最近邻回填）。

    只在 ROI 像素上插值（RBF 家族同样只在 ROI 内有非零支撑），
    大幅降低内存；ROI 外恒为 0。``extrapolation_fraction`` 记录
    触发凸包外回填的预测比例，解释指标时必须引用该值。
    """

    def __init__(
        self,
        target_shape: tuple[int, int],
        config: Config | None = None,
    ):
        self.target_shape = target_shape
        self.config = config or CONFIG
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None
        self._normalized: np.ndarray | None = None
        self._matrices: np.ndarray | None = None
        self._interpolator: LinearNDInterpolator | None = None
        self._roi_flat: np.ndarray | None = None
        self.total_queries = 0
        self.extrapolation_queries = 0

    @property
    def model_name(self) -> str:
        return "Linear"

    @property
    def extrapolation_fraction(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.extrapolation_queries / self.total_queries

    def _normalize(self, conditions: np.ndarray) -> np.ndarray:
        return (np.asarray(conditions, dtype=np.float64) - self.cond_lo) / self.cond_span

    def fit(self, conditions: np.ndarray, matrices: np.ndarray) -> None:
        conditions = np.asarray(conditions, dtype=np.float64)
        lo = conditions.min(axis=0)
        hi = conditions.max(axis=0)
        self.cond_lo = lo
        self.cond_span = np.where(hi > lo, hi - lo, 1.0)
        self._normalized = self._normalize(conditions)
        self._matrices = np.asarray(matrices)
        self.total_queries = 0
        self.extrapolation_queries = 0

        self._roi_flat = roi_mask_for_shape(self.target_shape, self.config).ravel()
        values = self._matrices.reshape(len(matrices), -1)[:, self._roi_flat]
        try:
            self._interpolator = LinearNDInterpolator(self._normalized, values)
        except (QhullError, ValueError) as exc:
            raise ModelFitError(
                f"线性插值基线拟合失败：训练工况无法构成三维三角剖分（{exc}）。"
                "线性插值要求至少 4 个不共面的工况；共线/共面工况下数学上不可用"
            ) from exc

    def predict_matrix(self, condition: Condition) -> np.ndarray:
        if self._interpolator is None:
            raise RuntimeError("模型尚未训练")
        query = self._normalize(condition.as_array().reshape(1, -1))
        values = self._interpolator(query)[0]
        self.total_queries += 1

        matrix = np.zeros(self.target_shape, dtype=np.float32)
        if np.isnan(values).any():
            # 凸包外无定义：最近邻回填并如实计数
            self.extrapolation_queries += 1
            distances = np.linalg.norm(self._normalized - query, axis=1)
            fallback = self._matrices[int(np.argmin(distances))]
            matrix[self._roi_flat.reshape(self.target_shape)] = fallback.ravel()[
                self._roi_flat
            ]
        else:
            matrix[self._roi_flat.reshape(self.target_shape)] = values
        return np.clip(matrix, 0.0, 1.0).astype(np.float32)
