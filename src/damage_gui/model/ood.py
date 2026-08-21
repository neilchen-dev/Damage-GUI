"""OOD（分布外）/ 预测可信度检测。

"输入合法"不代表"模型在这个位置有足够训练数据支撑"。本模块在
归一化工况空间中组合三种互补检测：

1. 最近邻距离：
       d = min_i || x - x_i ||
   d < 0.15        → High Confidence（插值区域）
   0.15 <= d < 0.3 → Medium Confidence
   d >= 0.3        → Low Confidence（外推区域，误差可能偏大）

2. SVD 内在维度凸包：先把共面/共线训练工况投影到真实内在子空间，
   再用 Delaunay 判断是否位于全局凸包内；同时检查查询点是否偏离该子空间。
3. 局部邻域凸包：全局凸包无法识别 L 形等凹分布内部的空洞，因此再检查
   查询点是否被最近的局部训练点包围。该检查是稀疏支撑启发式，失败时
   最高只给 Medium，不把凸包内部的大缺口误报为 High。

工程化软件不只是给出结果，还应该知道自己什么时候不可信。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from damage_gui.data.loader import Condition

LEVEL_HIGH = "high"
LEVEL_MEDIUM = "medium"
LEVEL_LOW = "low"

LEVEL_LABELS = {
    LEVEL_HIGH: "高（插值区域）",
    LEVEL_MEDIUM: "中（稀疏支撑区域）",
    LEVEL_LOW: "低（外推区域）",
}


@dataclass
class OODReport:
    """单个工况的预测可信度报告。"""

    distance: float
    level: str
    nearest_condition: dict[str, float]
    in_hull: bool | None = None
    local_support: bool | None = None

    @property
    def level_label(self) -> str:
        return LEVEL_LABELS.get(self.level, self.level)

    @property
    def is_reliable(self) -> bool:
        return self.level != LEVEL_LOW

    @property
    def is_extrapolation(self) -> bool:
        """是否存在明确的几何外推证据。"""
        return (
            self.level == LEVEL_LOW
            or self.in_hull is False
            or self.local_support is False
        )


class OODDetector:
    """最近邻距离 + SVD 凸包 + 局部邻域支撑的 OOD 检测器。"""

    def __init__(
        self,
        high_max: float = 0.15,
        medium_max: float = 0.3,
        use_hull: bool = True,
        use_local_support: bool = True,
        local_neighbors: int = 0,
        max_1d_gap_ratio: float = 2.5,
    ):
        if not (0.0 <= high_max <= medium_max):
            raise ValueError("OOD 阈值必须满足 0 <= high_max <= medium_max")
        if local_neighbors < 0:
            raise ValueError("local_neighbors 必须 >= 0（0 表示按内在维度自动选择）")
        if max_1d_gap_ratio <= 1.0:
            raise ValueError("max_1d_gap_ratio 必须 > 1")
        self.high_max = high_max
        self.medium_max = medium_max
        self.use_hull = use_hull
        self.use_local_support = use_local_support
        self.local_neighbors = int(local_neighbors)
        self.max_1d_gap_ratio = float(max_1d_gap_ratio)
        self._normalized: np.ndarray | None = None
        self._raw: np.ndarray | None = None
        self._delaunay: Delaunay | None = None
        self._hull_center: np.ndarray | None = None
        self._hull_basis: np.ndarray | None = None
        self._projected_points: np.ndarray | None = None
        self._projected_tree: cKDTree | None = None
        self._intrinsic_rank: int = 0
        self._subspace_tolerance: float = 1e-9
        self._interval_hull: tuple[float, float] | None = None
        self._reference_1d_spacing: float | None = None
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None

    def fit(self, conditions: np.ndarray) -> "OODDetector":
        """conditions: (n, d) 训练工况（通常 d=3）。"""
        conditions = np.asarray(conditions, dtype=np.float64)
        if conditions.ndim != 2 or conditions.shape[0] == 0:
            raise ValueError("OOD 检测器需要非空的 (n, 3) 工况数组")
        lo = conditions.min(axis=0)
        hi = conditions.max(axis=0)
        self.cond_lo = lo
        self.cond_span = np.where(hi > lo, hi - lo, 1.0)
        self._raw = conditions
        self._normalized = (conditions - lo) / self.cond_span
        self._delaunay = None
        self._hull_center = None
        self._hull_basis = None
        self._projected_points = None
        self._projected_tree = None
        self._intrinsic_rank = 0
        self._interval_hull = None
        self._reference_1d_spacing = None
        if self.use_hull:
            self._build_hull(self._normalized)
        return self

    def _build_hull(self, points: np.ndarray) -> None:
        """用 SVD 识别内在维度，再在该子空间构建凸包。"""
        center = points.mean(axis=0)
        centered = points - center
        _u, singular_values, vt = np.linalg.svd(centered, full_matrices=False)
        largest = float(singular_values[0]) if singular_values.size else 0.0
        tolerance = max(points.shape) * np.finfo(float).eps * max(largest, 1.0)
        rank = int(np.sum(singular_values > tolerance))

        self._hull_center = center
        self._intrinsic_rank = rank
        self._subspace_tolerance = max(1e-9, tolerance * 10.0)
        if rank == 0:
            self._hull_basis = np.zeros((points.shape[1], 0), dtype=np.float64)
            self._projected_points = np.zeros((1, 0), dtype=np.float64)
            return

        basis = vt[:rank].T
        projected = centered @ basis
        projected = np.unique(projected, axis=0)
        self._hull_basis = basis
        self._projected_points = projected
        self._projected_tree = cKDTree(projected)

        if rank == 1:
            values = np.sort(projected[:, 0])
            self._interval_hull = (float(values[0]), float(values[-1]))
            gaps = np.diff(values)
            positive = gaps[gaps > 1e-12]
            if positive.size:
                self._reference_1d_spacing = float(np.median(positive))
            return

        if projected.shape[0] < rank + 1:
            return
        try:
            self._delaunay = Delaunay(projected)
        except Exception:
            self._delaunay = None

    @property
    def is_fitted(self) -> bool:
        return self._normalized is not None

    @property
    def hull_available(self) -> bool:
        """凸包判定是否可用（训练集几何非退化时 True）。"""
        return (
            getattr(self, "_hull_basis", None) is not None
            and (
                getattr(self, "_intrinsic_rank", 0) == 0
                or self._delaunay is not None
                or self._interval_hull is not None
            )
        )

    @property
    def intrinsic_dimension(self) -> int | None:
        if getattr(self, "_hull_basis", None) is None:
            return None
        return int(getattr(self, "_intrinsic_rank", 0))

    def _normalize(self, condition: Condition) -> np.ndarray:
        return (condition.as_array() - self.cond_lo) / self.cond_span

    def _project_query(self, query: np.ndarray) -> tuple[np.ndarray, float] | None:
        center = getattr(self, "_hull_center", None)
        basis = getattr(self, "_hull_basis", None)
        if center is None or basis is None:
            return None
        delta = query - center
        projected = delta @ basis
        reconstructed = projected @ basis.T
        residual = float(np.linalg.norm(delta - reconstructed))
        return np.asarray(projected, dtype=np.float64), residual

    def _point_in_hull(self, query: np.ndarray) -> bool | None:
        """查询点是否在训练子空间及其全局凸包内。"""
        projection = self._project_query(query)
        if projection is None:
            return None
        sub_query, residual = projection
        if residual > getattr(self, "_subspace_tolerance", 1e-9):
            return False

        rank = int(getattr(self, "_intrinsic_rank", 0))
        if rank == 0:
            return True
        if self._interval_hull is not None:
            lo, hi = self._interval_hull
            return bool(lo - 1e-10 <= sub_query[0] <= hi + 1e-10)
        if self._delaunay is None:
            return None
        return bool(self._delaunay.find_simplex(sub_query, tol=1e-10) >= 0)

    def _has_local_support(
        self,
        query: np.ndarray,
        in_hull: bool | None,
    ) -> bool | None:
        """查询点是否被局部邻近训练点包围；用于识别全局凸包内空洞。"""
        if not getattr(self, "use_local_support", False) or in_hull is not True:
            return None
        projection = self._project_query(query)
        points = getattr(self, "_projected_points", None)
        if projection is None or points is None:
            return None
        sub_query, _residual = projection
        rank = int(getattr(self, "_intrinsic_rank", 0))
        if rank == 0:
            return True

        if rank == 1:
            values = np.sort(points[:, 0])
            position = int(np.searchsorted(values, sub_query[0]))
            if position == 0 or position == len(values):
                return True
            gap = float(values[position] - values[position - 1])
            reference = getattr(self, "_reference_1d_spacing", None)
            if reference is None or reference <= 0:
                return None
            return gap <= getattr(self, "max_1d_gap_ratio", 2.5) * reference

        count = len(points)
        # 真实三维规则网格的随机留出校准表明 2*(rank+1)=8 会因近邻
        # 等距并列的截断次序，把少量正常网格点误报为局部空洞；10 个近邻
        # 可消除该误报。3*rank+1 在二维时仍只取 7 点，保持对密集 L 形
        # 凹口的识别能力，不会用过远点跨越小空洞。
        automatic = 3 * rank + 1
        requested = int(getattr(self, "local_neighbors", 0))
        neighbors = min(count, requested or automatic)
        if neighbors >= count or neighbors < rank + 1:
            return True

        tree = getattr(self, "_projected_tree", None) or cKDTree(points)
        _distances, indices = tree.query(sub_query, k=neighbors)
        local_points = np.unique(points[np.atleast_1d(indices)], axis=0)
        if len(local_points) < rank + 1:
            return False
        try:
            local_hull = Delaunay(local_points)
        except Exception:
            return False
        return bool(local_hull.find_simplex(sub_query, tol=1e-10) >= 0)

    def report(self, condition: Condition) -> OODReport:
        """评估单个工况的预测可信度。"""
        if not self.is_fitted:
            raise RuntimeError("OOD 检测器尚未拟合")
        query = self._normalize(condition)
        distances = np.linalg.norm(self._normalized - query, axis=1)
        index = int(np.argmin(distances))
        distance = float(distances[index])

        in_hull = self._point_in_hull(query)
        local_support = self._has_local_support(query, in_hull)

        if distance < self.high_max:
            level = LEVEL_HIGH
        elif distance < self.medium_max:
            level = LEVEL_MEDIUM
        else:
            level = LEVEL_LOW
        # 凸包外一定是纯外推（插值不可达），不给 High；
        # 距离本来就大的点维持 Low 不变
        if (in_hull is False or local_support is False) and level == LEVEL_HIGH:
            level = LEVEL_MEDIUM

        nearest_raw = self._raw[index]
        nearest = {
            "h": float(nearest_raw[0]),
            "v": float(nearest_raw[1]),
            "deg": float(nearest_raw[2]),
        }
        return OODReport(
            distance=distance,
            level=level,
            nearest_condition=nearest,
            in_hull=in_hull,
            local_support=local_support,
        )

    def describe(self, report: OODReport) -> str:
        """生成 GUI 展示用的可信度描述文本。"""
        nearest = report.nearest_condition
        lines = [
            f"模型可信度：{report.level_label}",
            f"最近训练工况距离：{report.distance:.3f}",
            (
                f"最近工况：h={nearest['h']:g}, v={nearest['v']:g}, "
                f"deg={nearest['deg']:g}"
            ),
        ]
        if report.in_hull is False:
            lines.append(
                "当前工况位于训练工况凸包之外（插值不可达，纯外推预测）"
            )
        if report.local_support is False:
            lines.append(
                "当前工况虽在全局凸包内，但未被局部邻近训练点包围（可能位于数据空洞）"
            )
        if report.level == LEVEL_LOW:
            lines.append(
                "⚠ 当前工况位于训练数据覆盖边缘，该结果可能存在较大的外推误差"
            )
        return "\n".join(lines)
