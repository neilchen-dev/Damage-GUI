"""基于数据驱动的毁伤效能快速评估 GUI（重构版 v2）。

核心思路（相对旧版的变化）：
- 120 个工况在 (h, v, deg) 空间构成规则网格，最适合的模型不是逐点回归，
  而是在工况空间对整幅毁伤矩阵做插值（RBF 插值场）。
- 蒙特卡洛降噪（双边滤波）：原始矩阵带像素级仿真噪声（相邻工况逐点差异
  P95 达 50%），读入时双边滤波去噪——只平滑数值相近的邻域，毁伤核心的
  真实峰值（~1.0）完整保留（高斯平滑会把峰值压到 0.38，已弃用）。
- 场级评估口径：降噪后的真值仍残留像素噪声，逐点指标在"真值与预测做同样
  高斯低通（eval_smoothing_sigma）"的局部平均场上计算；热力图展示保真。
- 质心对齐插值：先把各工况图案平移到质心居中的标准位置再插值形状，
  质心轨迹单独插值，预测时平移回去——消除图案随工况移动产生的"重影"。
- 核心评估指标：主要毁伤区 (damage > 0.05) 的平均相对误差与 P95 混合误差
  （相对误差与绝对误差取宽），目标为 20% 以内。
"""
from __future__ import annotations

import math
import re
import sys
import traceback
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ProgressCallback = Callable[[int, int, str], None]

import joblib
import matplotlib
import numpy as np
import pandas as pd
import tkinter as tk
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import center_of_mass as ndi_center_of_mass
from scipy.ndimage import gaussian_filter
from scipy.ndimage import shift as ndi_shift
from scipy.ndimage import zoom
from sklearn.metrics import (
    max_error,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from tkinter import filedialog, messagebox, ttk

matplotlib.use("TkAgg")
from matplotlib import font_manager, ticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from damage_gui.aim_optimization import AimOptimizationResult, optimize_aim

# 毁伤强度：单色调科学渐变，浅色=未毁伤，深蓝=完全毁伤（对色弱友好，无廉价感）
DAMAGE_CMAP = "YlGnBu"
# 误差场：发散色带，0 误差为白色，正负误差用柔和的红/蓝区分
ERROR_CMAP = "RdBu_r"


@dataclass(frozen=True)
class Config:
    coord_min: float = -236.0
    coord_max: float = 236.0
    target_shape: tuple[int, int] = (473, 473)

    # 有效建模区域 ROI：只在该矩形区域内插值和预测，ROI 外置 0。
    use_roi: bool = True
    roi_x_min: float = -30.0
    roi_x_max: float = 30.0
    roi_y_min: float = -60.0
    roi_y_max: float = 60.0

    random_state: int = 42
    test_size: float = 0.2

    # 蒙特卡洛降噪（双边滤波）：原始毁伤矩阵带有像素级仿真噪声（实测单幅矩阵
    # 做 1 像素平滑自身就变化 18%，相邻工况逐点差异 P95 达 50%）。
    # 双边滤波只平滑数值相近的邻域，遇到真实的强度突变（如接近 1.0 的毁伤核心
    # 边缘）会保留而不是抹平——实测峰值保留约 100%（高斯 sigma=3 会把峰值
    # 0.999 压到 0.377）。训练与展示统一使用双边滤波后的场。
    denoise_sigma_spatial: float = 3.0
    denoise_sigma_range: float = 0.15
    denoise_radius: int = 6
    # 场级评估口径：即使双边滤波后，真值仍残留像素级噪声（P95 约 40%），
    # 拿完美预测对比带噪真值也会"测出"同量级假误差，故逐点指标在
    # "局部平均场"上计算：真值与预测先做同样的高斯低通（eval_smoothing_sigma）
    # 再逐点比较。这衡量毁伤概率场的真实一致性；热力图展示不受影响（保真）。
    eval_smoothing_sigma: float = 3.0

    # RBF 插值场参数：kernel 为 scipy.interpolate.RBFInterpolator 的核函数，
    # smoothing=0 表示精确插值（训练工况上零误差）。
    rbf_kernel: str = "thin_plate_spline"
    rbf_smoothing: float = 0.0
    # 质心对齐插值：毁伤图案随工况平移时，逐像素直接插值会产生"重影"
    # （新旧位置各留一个变淡的影子，图案该在的位置反而预测为 0）。
    # 开启后先把每幅矩阵平移到质心居中的标准位置再插值形状，
    # 质心位置单独用 RBF 插值，预测时把形状平移回去。
    align_patterns: bool = True
    align_window_margin: int = 16

    display_threshold: float = 0.08
    crop_margin: int = 10
    export_dpi: int = 120
    eval_area_threshold: float = 0.01
    eval_focus_thresholds: tuple[float, float] = (0.01, 0.05)
    # 相对误差只在主要毁伤区域 damage > relative_error_threshold 内统计；
    # 核心指标为平均相对误差与 P95 混合误差，目标 < relative_error_target。
    relative_error_threshold: float = 0.05
    relative_error_target: float = 0.20
    # 混合误差 = |pred - true| / max(true, hybrid_error_floor)。
    # 毁伤区边缘 true 刚过 0.05 的点，边界偏移 1 像素就会让纯相对误差爆到 100%+，
    # 但其绝对误差可忽略；分母加下限后等价于"相对误差 < 20% 或绝对误差 < 0.05 即达标"，
    # 使指标反映毁伤强度预测能力而非亚像素级边界定位能力。
    hybrid_error_floor: float = 0.25

    # 现代轻量化配色：浅冷灰底 + 唯一主题色（深科技蓝），状态色柔和不刺眼
    ui_bg: str = "#F5F7FA"
    ui_panel_bg: str = "#FFFFFF"
    ui_soft_bg: str = "#EEF2F7"
    ui_border: str = "#E2E8F0"
    ui_shadow: str = "#E3E8F0"
    ui_primary: str = "#1E3A8A"
    ui_primary_dark: str = "#172E6E"
    ui_accent: str = "#1E3A8A"
    ui_text: str = "#1E293B"
    ui_muted: str = "#64748B"
    ui_header_bg: str = "#1E3A8A"
    ui_header_fg: str = "#FFFFFF"
    ui_header_muted: str = "#B6C3E4"
    ui_success: str = "#15803D"
    ui_danger: str = "#B91C1C"
    ui_busy: str = "#B45309"


CONFIG = Config()
APP_TITLE = "基于数据驱动的毁伤效能快速评估方法研究"

FILENAME_PATTERN = re.compile(r"DamageMatrix_([FMP])_h_(\d+)_v_(\d+)_deg_(\d+)$")


def configure_matplotlib_fonts() -> None:
    candidate_fonts = [
        (Path(r"C:\Windows\Fonts\msyh.ttc"), "Microsoft YaHei"),
        (Path(r"C:\Windows\Fonts\msyh.ttf"), "Microsoft YaHei"),
        (Path(r"C:\Windows\Fonts\simhei.ttf"), "SimHei"),
        (Path(r"C:\Windows\Fonts\simsun.ttc"), "SimSun"),
    ]

    selected_fonts: list[str] = []
    for font_path, font_name in candidate_fonts:
        if font_path.exists():
            try:
                font_manager.fontManager.addfont(str(font_path))
                selected_fonts.append(font_name)
            except Exception:
                continue

    if not selected_fonts:
        selected_fonts = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = selected_fonts + [
        "SimHei",
        "Microsoft YaHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    warnings.filterwarnings(
        "ignore",
        message=r".*Glyph .* missing from font\(s\) DejaVu Sans.*",
        category=UserWarning,
    )


configure_matplotlib_fonts()


def resource_path(filename: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).with_name(filename)


def app_base_dir() -> Path:
    """统一应用根目录（兼容 PyInstaller frozen 和源码运行）。

    - 源码运行: 返回脚本所在目录
    - exe 运行: 返回 exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resolve_icon_paths() -> tuple[Path | None, Path | None]:
    ico_path = resource_path("damage_app_icon.ico")
    png_path = resource_path("damage_app_icon.png")
    return (
        ico_path if ico_path.exists() else None,
        png_path if png_path.exists() else None,
    )


@dataclass(frozen=True)
class Condition:
    h: float
    v: float
    deg: float

    def as_key(self) -> tuple[float, float, float]:
        return (round(self.h, 1), round(self.v, 1), round(self.deg, 1))

    def as_dict(self) -> dict[str, float]:
        return {"h": self.h, "v": self.v, "deg": self.deg}

    def as_array(self) -> np.ndarray:
        return np.array([self.h, self.v, self.deg], dtype=np.float64)


@dataclass
class DamageRecord:
    level: str
    condition: Condition
    path: Path


class DamageDataManager:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def scan_records(self) -> list[DamageRecord]:
        if not self.data_dir.exists():
            raise FileNotFoundError(f"数据目录不存在: {self.data_dir}")

        records: list[DamageRecord] = []
        for path in sorted(self.data_dir.iterdir()):
            match = FILENAME_PATTERN.match(path.name)
            if not match:
                continue
            level, h_raw, v_raw, deg_raw = match.groups()
            condition = Condition(
                h=float(h_raw) / 10.0,
                v=float(v_raw) / 10.0,
                deg=float(deg_raw) / 10.0,
            )
            records.append(DamageRecord(level=level, condition=condition, path=path))
        if not records:
            raise FileNotFoundError(f"未在 {self.data_dir} 中找到 DamageMatrix 文件")
        return records

    def get_level_records(self, level: str) -> list[DamageRecord]:
        records = [record for record in self.scan_records() if record.level == level]
        if not records:
            raise ValueError(f"数据目录中没有等级 {level} 的矩阵文件")
        return records

    def find_record(self, level: str, condition: Condition) -> DamageRecord | None:
        target = condition.as_key()
        for record in self.get_level_records(level):
            if record.condition.as_key() == target:
                return record
        return None


def bilateral_filter(
    image: np.ndarray,
    sigma_spatial: float,
    sigma_range: float,
    radius: int,
) -> np.ndarray:
    """双边滤波：空间邻近且数值相近的像素才互相平均。

    像素值差异大的邻域（如毁伤核心边缘）权重被压低，从而在平滑
    蒙特卡洛噪声的同时保留真实的强度突变。用位移+向量化实现。
    """
    image = np.asarray(image, dtype=np.float64)
    padded = np.pad(image, radius, mode="constant", constant_values=0.0)
    acc = np.zeros_like(image)
    weight_sum = np.zeros_like(image)

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = padded[
                radius + dy: radius + dy + image.shape[0],
                radius + dx: radius + dx + image.shape[1],
            ]
            spatial_w = math.exp(-(dy * dy + dx * dx) / (2 * sigma_spatial ** 2))
            range_w = np.exp(-((shifted - image) ** 2) / (2 * sigma_range ** 2))
            weight = spatial_w * range_w
            acc += weight * shifted
            weight_sum += weight

    return (acc / np.maximum(weight_sum, 1e-12)).astype(np.float32)


def read_damage_matrix(path: Path) -> np.ndarray:
    frame = pd.read_csv(path, sep="\t", encoding="gbk", header=None, skiprows=1)
    frame = frame.dropna(axis=1, how="all")
    matrix = frame.to_numpy(dtype=np.float32)
    matrix = normalize_matrix_shape(matrix, CONFIG.target_shape)
    if CONFIG.denoise_radius > 0:
        matrix = bilateral_filter(
            matrix,
            CONFIG.denoise_sigma_spatial,
            CONFIG.denoise_sigma_range,
            CONFIG.denoise_radius,
        )
    return matrix


def normalize_matrix_shape(matrix: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.shape == target_shape:
        return matrix
    zoom_factors = (
        target_shape[0] / matrix.shape[0],
        target_shape[1] / matrix.shape[1],
    )
    resized = zoom(matrix, zoom_factors, order=1)
    if resized.shape != target_shape:
        corrected = np.zeros(target_shape, dtype=np.float32)
        rows = min(target_shape[0], resized.shape[0])
        cols = min(target_shape[1], resized.shape[1])
        corrected[:rows, :cols] = resized[:rows, :cols]
        resized = corrected
    return np.clip(resized.astype(np.float32), 0.0, 1.0)


def coordinate_axes(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = shape
    x_axis = np.linspace(CONFIG.coord_min, CONFIG.coord_max, cols, dtype=np.float32)
    y_axis = np.linspace(CONFIG.coord_min, CONFIG.coord_max, rows, dtype=np.float32)
    return x_axis, y_axis


def coordinate_grids(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    x_axis, y_axis = coordinate_axes(shape)
    return np.meshgrid(x_axis, y_axis)


def roi_mask_for_shape(shape: tuple[int, int]) -> np.ndarray:
    """返回有效建模区域 ROI 的布尔掩膜（ROI 外预测值恒为 0）。"""
    if not CONFIG.use_roi:
        return np.ones(shape, dtype=bool)

    grid_x, grid_y = coordinate_grids(shape)
    return (
        (grid_x >= CONFIG.roi_x_min)
        & (grid_x <= CONFIG.roi_x_max)
        & (grid_y >= CONFIG.roi_y_min)
        & (grid_y <= CONFIG.roi_y_max)
    )


def roi_description() -> str:
    if not CONFIG.use_roi:
        return "全矩阵"
    return (
        f"x=[{CONFIG.roi_x_min:g}, {CONFIG.roi_x_max:g}], "
        f"y=[{CONFIG.roi_y_min:g}, {CONFIG.roi_y_max:g}]"
    )


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
    ):
        self.kernel = kernel
        self.smoothing = smoothing
        self.target_shape = target_shape
        self.align = align
        self.cond_lo: np.ndarray | None = None
        self.cond_span: np.ndarray | None = None
        self.window_rows: tuple[int, int] | None = None
        self.window_cols: tuple[int, int] | None = None
        self.shape_interpolator: RBFInterpolator | None = None
        self.centroid_interpolator: RBFInterpolator | None = None

    @property
    def _center(self) -> tuple[float, float]:
        return ((self.target_shape[0] - 1) / 2.0, (self.target_shape[1] - 1) / 2.0)

    def _normalize(self, conditions: np.ndarray) -> np.ndarray:
        return (np.asarray(conditions, dtype=np.float64) - self.cond_lo) / self.cond_span

    def _compute_window(self) -> None:
        """插值窗口 = ROI 外包框向外扩 margin，保证对齐后的图案不越界。"""
        roi = roi_mask_for_shape(self.target_shape)
        rows = np.flatnonzero(roi.any(axis=1))
        cols = np.flatnonzero(roi.any(axis=0))
        margin = CONFIG.align_window_margin
        self.window_rows = (
            max(0, int(rows[0]) - margin),
            min(self.target_shape[0], int(rows[-1]) + margin + 1),
        )
        self.window_cols = (
            max(0, int(cols[0]) - margin),
            min(self.target_shape[1], int(cols[-1]) + margin + 1),
        )

    def _matrix_centroid(self, matrix: np.ndarray) -> tuple[float, float]:
        if float(matrix.sum()) <= 1e-6:
            return self._center
        cy, cx = ndi_center_of_mass(matrix)
        return float(cy), float(cx)

    def fit(self, conditions: np.ndarray, matrices: np.ndarray) -> None:
        """conditions: (n, 3)；matrices: (n, rows, cols) 完整毁伤矩阵。"""
        conditions = np.asarray(conditions, dtype=np.float64)
        lo = conditions.min(axis=0)
        hi = conditions.max(axis=0)
        self.cond_lo = lo
        self.cond_span = np.where(hi > lo, hi - lo, 1.0)
        self._compute_window()

        r0, r1 = self.window_rows
        c0, c1 = self.window_cols
        center_r, center_c = self._center
        count = len(matrices)
        centroids = np.zeros((count, 2), dtype=np.float64)
        shapes = np.zeros((count, (r1 - r0) * (c1 - c0)), dtype=np.float64)

        for i, matrix in enumerate(matrices):
            cy, cx = self._matrix_centroid(matrix)
            centroids[i] = (cy, cx)
            if self.align:
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

        normalized = self._normalize(conditions)
        self.shape_interpolator = RBFInterpolator(
            normalized,
            shapes,
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

    def predict_matrix(self, condition: Condition) -> np.ndarray:
        if self.shape_interpolator is None:
            raise RuntimeError("模型尚未训练")
        query = self._normalize(condition.as_array().reshape(1, -1))

        r0, r1 = self.window_rows
        c0, c1 = self.window_cols
        window = np.clip(self.shape_interpolator(query)[0], 0.0, 1.0)
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

        matrix[~roi_mask_for_shape(self.target_shape)] = 0.0
        return np.clip(matrix, 0.0, 1.0).astype(np.float32)


@dataclass
class ModelBundle:
    level: str
    data_dir: str
    target_shape: tuple[int, int]
    config: dict
    model: RBFDamageField
    train_conditions: list[dict[str, float]]
    test_conditions: list[dict[str, float]]
    accuracy_report: pd.DataFrame = field(default_factory=pd.DataFrame)
    condition_report: pd.DataFrame = field(default_factory=pd.DataFrame)


def evaluation_fields(
    true_matrix: np.ndarray,
    pred_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """场级评估口径：真值与预测做同样的高斯低通（局部平均）后再逐点比较。

    降噪后的真值仍残留像素级蒙特卡洛噪声，直接逐点对比会把真值自身的
    噪声计入模型误差。展示用的热力图不经过此处理（保真）。
    """
    sigma = CONFIG.eval_smoothing_sigma
    if sigma <= 0:
        return true_matrix, pred_matrix
    return (
        gaussian_filter(true_matrix, sigma).astype(np.float32),
        gaussian_filter(pred_matrix, sigma).astype(np.float32),
    )


def safe_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if y_true.size == 0:
        return float("nan")
    if np.allclose(y_true, y_true[0]):
        return float("nan")
    return float(r2_score(y_true, y_pred))


def metric_row(
    scope: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    area_threshold: float,
) -> dict[str, float | str]:
    """计算误差指标。

    相对误差只在主要毁伤区域 damage > CONFIG.relative_error_threshold 内统计，
    避免真实值接近 0 时相对误差被异常放大。
    核心指标为平均相对误差与 P95 混合误差（混合误差见 Config.hybrid_error_floor 注释），
    最大相对误差作为参考项保留。
    对 overall / roi_overall 等非主要毁伤区域统计，相对误差字段置为 NaN。
    """
    y_true = np.asarray(y_true, dtype=np.float32)
    y_pred = np.asarray(y_pred, dtype=np.float32)
    if y_true.size == 0:
        return {
            "scope": scope,
            "points": 0,
            "MSE": np.nan,
            "RMSE": np.nan,
            "MAE": np.nan,
            "R2": np.nan,
            "MaxError": np.nan,
            "TrueDamageAreaRatio": np.nan,
            "PredDamageAreaRatio": np.nan,
            "AreaRatioGap": np.nan,
            "MeanRelativeError": np.nan,
            "P90RelativeError": np.nan,
            "MaxRelativeError": np.nan,
            "P95HybridError": np.nan,
            "MaxHybridError": np.nan,
            "HybridAccuracyInTarget": np.nan,
        }

    mse_value = float(mean_squared_error(y_true, y_pred))
    rmse_value = float(math.sqrt(mse_value))
    mae_value = float(mean_absolute_error(y_true, y_pred))
    true_ratio = float(np.mean(y_true > area_threshold))
    pred_ratio = float(np.mean(y_pred > area_threshold))

    if area_threshold >= CONFIG.relative_error_threshold and np.all(y_true > area_threshold):
        abs_error = np.abs(y_pred - y_true)
        relative_error = abs_error / y_true
        hybrid_error = abs_error / np.maximum(y_true, CONFIG.hybrid_error_floor)
        mean_relative_error = float(np.mean(relative_error))
        p90_relative_error = float(np.quantile(relative_error, 0.90))
        max_relative_error = float(np.max(relative_error))
        p95_hybrid_error = float(np.quantile(hybrid_error, 0.95))
        max_hybrid_error = float(np.max(hybrid_error))
        hybrid_accuracy = float(np.mean(hybrid_error < CONFIG.relative_error_target))
    else:
        mean_relative_error = np.nan
        p90_relative_error = np.nan
        max_relative_error = np.nan
        p95_hybrid_error = np.nan
        max_hybrid_error = np.nan
        hybrid_accuracy = np.nan

    return {
        "scope": scope,
        "points": int(y_true.size),
        "MSE": mse_value,
        "RMSE": rmse_value,
        "MAE": mae_value,
        "R2": safe_r2(y_true, y_pred),
        "MaxError": float(max_error(y_true, y_pred)),
        "TrueDamageAreaRatio": true_ratio,
        "PredDamageAreaRatio": pred_ratio,
        "AreaRatioGap": float(pred_ratio - true_ratio),
        "MeanRelativeError": mean_relative_error,
        "P90RelativeError": p90_relative_error,
        "MaxRelativeError": max_relative_error,
        "P95HybridError": p95_hybrid_error,
        "MaxHybridError": max_hybrid_error,
        "HybridAccuracyInTarget": hybrid_accuracy,
    }


def format_core_metrics(accuracy_report: pd.DataFrame) -> str:
    """格式化评估摘要：核心指标为平均相对误差与 P95 混合误差。"""
    if accuracy_report.empty:
        return ""

    lines: list[str] = []
    target = CONFIG.relative_error_target
    focus_scope = f"damage_gt_{CONFIG.relative_error_threshold:.2f}"
    focus = accuracy_report[accuracy_report["scope"] == focus_scope]
    if not focus.empty:
        row = focus.iloc[0]
        mean_re = row.get("MeanRelativeError", np.nan)
        p95_hybrid = row.get("P95HybridError", np.nan)
        if not pd.isna(mean_re):
            mean_flag = "✔达标" if mean_re < target else "✘未达标"
            hybrid_flag = "✔达标" if p95_hybrid < target else "✘未达标"
            lines.append(
                f"核心指标 (毁伤区 damage>{CONFIG.relative_error_threshold:g}, 目标<{target:.0%})"
            )
            lines.append(f"平均相对误差 = {mean_re:.2%}  {mean_flag}")
            lines.append(f"P95混合误差 = {p95_hybrid:.2%}  {hybrid_flag}")
            lines.append(
                f"点达标率(混合<{target:.0%}) = {row['HybridAccuracyInTarget']:.2%}"
            )
            lines.append(
                f"参考: 最大相对误差 = {row['MaxRelativeError']:.2%}, "
                f"P90相对误差 = {row['P90RelativeError']:.2%}, "
                f"最大混合误差 = {row['MaxHybridError']:.2%}"
            )
            lines.append(
                f"(混合误差: 相对误差与 绝对误差/{CONFIG.hybrid_error_floor:g} 取小者; "
                f"评估口径: σ={CONFIG.eval_smoothing_sigma:g} 局部平均场)"
            )
            lines.append("")

    for _, row in accuracy_report.iterrows():
        lines.append(
            f"{row['scope']}: RMSE={row['RMSE']:.4f} "
            f"MAE={row['MAE']:.4f} R2={row['R2']:.4f}"
        )
    return "\n".join(lines).strip()


class DamageModelService:

    def __init__(self, data_manager: DamageDataManager):
        self.data_manager = data_manager

    def train_bundle(
        self,
        level: str,
        progress: ProgressCallback | None = None,
    ) -> ModelBundle:
        records = self.data_manager.get_level_records(level)
        if len(records) < 5:
            raise ValueError("可训练工况过少，至少需要 5 个工况")

        train_records, test_records = self._split_records(records)

        conditions, matrices = self._load_matrices(train_records, progress, "读取训练矩阵")
        if progress is not None:
            progress(0, 1, "拟合 RBF 插值场...")
        model = RBFDamageField(
            kernel=CONFIG.rbf_kernel,
            smoothing=CONFIG.rbf_smoothing,
            target_shape=CONFIG.target_shape,
            align=CONFIG.align_patterns,
        )
        model.fit(conditions, matrices)

        accuracy_report, condition_report = self._evaluate(
            level, model, test_records, progress
        )

        return ModelBundle(
            level=level,
            data_dir=str(self.data_manager.data_dir),
            target_shape=CONFIG.target_shape,
            config=CONFIG.__dict__.copy(),
            model=model,
            train_conditions=[record.condition.as_dict() for record in train_records],
            test_conditions=[record.condition.as_dict() for record in test_records],
            accuracy_report=accuracy_report,
            condition_report=condition_report,
        )

    def _split_records(
        self,
        records: list[DamageRecord],
    ) -> tuple[list[DamageRecord], list[DamageRecord]]:
        if len(records) <= 6:
            shuffled = list(records)
            rng = np.random.default_rng(CONFIG.random_state)
            rng.shuffle(shuffled)
            return shuffled[:-1], shuffled[-1:]

        train_records, test_records = train_test_split(
            records,
            test_size=CONFIG.test_size,
            random_state=CONFIG.random_state,
            shuffle=True,
        )
        return list(train_records), list(test_records)

    @staticmethod
    def _load_matrices(
        records: list[DamageRecord],
        progress: ProgressCallback | None = None,
        stage: str = "读取矩阵",
    ) -> tuple[np.ndarray, np.ndarray]:
        conditions = np.zeros((len(records), 3), dtype=np.float64)
        matrices = np.zeros((len(records), *CONFIG.target_shape), dtype=np.float32)
        for i, record in enumerate(records):
            matrices[i] = read_damage_matrix(record.path)
            conditions[i] = record.condition.as_array()
            if progress is not None:
                progress(i + 1, len(records), f"{stage} {i + 1}/{len(records)}")
        return conditions, matrices

    def predict_matrix(self, bundle: ModelBundle, condition: Condition) -> np.ndarray:
        return bundle.model.predict_matrix(condition)

    def _evaluate(
        self,
        level: str,
        model: RBFDamageField,
        test_records: list[DamageRecord],
        progress: ProgressCallback | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        overall_true_parts: list[np.ndarray] = []
        overall_pred_parts: list[np.ndarray] = []
        scope_true_parts: dict[float, list[np.ndarray]] = {
            threshold: [] for threshold in CONFIG.eval_focus_thresholds
        }
        scope_pred_parts: dict[float, list[np.ndarray]] = {
            threshold: [] for threshold in CONFIG.eval_focus_thresholds
        }
        condition_rows: list[dict[str, float | str]] = []

        for test_index, record in enumerate(test_records):
            if progress is not None:
                progress(
                    test_index + 1,
                    len(test_records),
                    f"评估测试工况 {test_index + 1}/{len(test_records)}",
                )
            true_matrix = read_damage_matrix(record.path)
            pred_matrix = model.predict_matrix(record.condition)
            eval_true, eval_pred = evaluation_fields(true_matrix, pred_matrix)

            y_true = eval_true.ravel()
            y_pred = eval_pred.ravel()
            roi_flat_mask = roi_mask_for_shape(true_matrix.shape).ravel()

            overall_true_parts.append(y_true)
            overall_pred_parts.append(y_pred)

            row = {
                "level": level,
                "h": record.condition.h,
                "v": record.condition.v,
                "deg": record.condition.deg,
                "ROI": roi_description(),
            }
            row.update(metric_row("overall", y_true, y_pred, CONFIG.eval_area_threshold))

            roi_metrics = metric_row(
                "roi_overall",
                y_true[roi_flat_mask],
                y_pred[roi_flat_mask],
                CONFIG.eval_area_threshold,
            )
            row["ROI_MSE"] = roi_metrics["MSE"]
            row["ROI_RMSE"] = roi_metrics["RMSE"]
            row["ROI_MAE"] = roi_metrics["MAE"]
            row["ROI_R2"] = roi_metrics["R2"]
            row["ROI_MaxError"] = roi_metrics["MaxError"]
            row["ROI_TrueDamageAreaRatio"] = roi_metrics["TrueDamageAreaRatio"]
            row["ROI_PredDamageAreaRatio"] = roi_metrics["PredDamageAreaRatio"]
            row["ROI_AreaRatioGap"] = roi_metrics["AreaRatioGap"]

            for threshold in CONFIG.eval_focus_thresholds:
                mask = y_true > threshold
                scope_true = y_true[mask]
                scope_pred = y_pred[mask]
                scope_metrics = metric_row(
                    f"damage_gt_{threshold:.2f}",
                    scope_true,
                    scope_pred,
                    threshold,
                )
                suffix = f"_gt_{threshold:.2f}"
                row[f"MSE{suffix}"] = scope_metrics["MSE"]
                row[f"RMSE{suffix}"] = scope_metrics["RMSE"]
                row[f"MAE{suffix}"] = scope_metrics["MAE"]
                row[f"R2{suffix}"] = scope_metrics["R2"]
                row[f"MaxError{suffix}"] = scope_metrics["MaxError"]
                row[f"TrueAreaRatio{suffix}"] = scope_metrics["TrueDamageAreaRatio"]
                row[f"PredAreaRatio{suffix}"] = scope_metrics["PredDamageAreaRatio"]
                row[f"MeanRelativeError{suffix}"] = scope_metrics["MeanRelativeError"]
                row[f"P90RelativeError{suffix}"] = scope_metrics["P90RelativeError"]
                row[f"MaxRelativeError{suffix}"] = scope_metrics["MaxRelativeError"]
                row[f"P95HybridError{suffix}"] = scope_metrics["P95HybridError"]
                row[f"MaxHybridError{suffix}"] = scope_metrics["MaxHybridError"]
                row[f"HybridAccuracyInTarget{suffix}"] = scope_metrics["HybridAccuracyInTarget"]

                scope_true_parts[threshold].append(scope_true)
                scope_pred_parts[threshold].append(scope_pred)

            condition_rows.append(row)

        overall_true = np.concatenate(overall_true_parts)
        overall_pred = np.concatenate(overall_pred_parts)

        roi_flat_mask = roi_mask_for_shape(CONFIG.target_shape).ravel()
        repeated_roi_mask = np.tile(roi_flat_mask, len(test_records))

        accuracy_rows = [
            metric_row("overall", overall_true, overall_pred, CONFIG.eval_area_threshold),
            metric_row(
                "roi_overall",
                overall_true[repeated_roi_mask],
                overall_pred[repeated_roi_mask],
                CONFIG.eval_area_threshold,
            ),
        ]

        for threshold in CONFIG.eval_focus_thresholds:
            threshold_true = np.concatenate(scope_true_parts[threshold])
            threshold_pred = np.concatenate(scope_pred_parts[threshold])
            accuracy_rows.append(
                metric_row(
                    f"damage_gt_{threshold:.2f}",
                    threshold_true,
                    threshold_pred,
                    threshold,
                )
            )

        accuracy_report = pd.DataFrame(accuracy_rows)
        accuracy_report.insert(0, "level", level)
        condition_report = pd.DataFrame(condition_rows)
        return accuracy_report, condition_report


def find_crop_bounds(
    matrices: list[np.ndarray],
    threshold: float,
    margin: int,
) -> tuple[int, int, int, int]:
    combined = np.zeros_like(matrices[0], dtype=bool)
    for matrix in matrices:
        combined |= np.asarray(matrix) > threshold

    if not np.any(combined):
        return 0, matrices[0].shape[0], 0, matrices[0].shape[1]

    rows, cols = np.where(combined)
    row_min = max(0, int(rows.min()) - margin)
    row_max = min(matrices[0].shape[0], int(rows.max()) + margin + 1)
    col_min = max(0, int(cols.min()) - margin)
    col_max = min(matrices[0].shape[1], int(cols.max()) + margin + 1)
    return row_min, row_max, col_min, col_max


def crop_matrix_and_extent(
    matrix: np.ndarray,
    bounds: tuple[int, int, int, int],
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    row_min, row_max, col_min, col_max = bounds
    x_axis, y_axis = coordinate_axes(matrix.shape)
    cropped = matrix[row_min:row_max, col_min:col_max]
    extent = (
        float(x_axis[col_min]),
        float(x_axis[col_max - 1]),
        float(y_axis[row_min]),
        float(y_axis[row_max - 1]),
    )
    return cropped, extent


def _style_heatmap_axis(axis, title: str, show_y_axis: bool = True) -> None:
    """极简坐标轴：只在最左图保留 y 轴，刻度稀疏、无网格、细边框。"""
    axis.set_facecolor(CONFIG.ui_bg)
    axis.set_title(title, fontsize=10.5, color=CONFIG.ui_text, pad=8)
    axis.set_xlabel("x (m)", fontsize=8.5, color=CONFIG.ui_muted)
    axis.xaxis.set_major_locator(ticker.MaxNLocator(nbins=5, steps=[1, 2, 4, 5, 10]))
    axis.grid(False)

    if show_y_axis:
        axis.set_ylabel("y (m)", fontsize=8.5, color=CONFIG.ui_muted)
        axis.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5, steps=[1, 2, 4, 5, 10]))
    else:
        axis.get_yaxis().set_visible(False)

    axis.tick_params(colors=CONFIG.ui_muted, labelsize=8, length=3, width=0.6)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(CONFIG.ui_border)
        axis.spines[side].set_linewidth(0.7)


def _add_percent_colorbar(figure, image, axis, label: str, zero_center: bool = False) -> None:
    """纤细、留白充分的颜色条。

    zero_center=True 用于双向发散色带（误差图）：刻度取对称等分，保证 0% 一定
    落在刻度上，并在零点处画一条指示线，方便辨识"绝对无误差"区域。
    """
    colorbar = figure.colorbar(image, ax=axis, shrink=0.8, aspect=30, pad=0.06)
    colorbar.ax.set_ylabel(label, rotation=90, fontsize=8.5, color=CONFIG.ui_muted)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=7.5, colors=CONFIG.ui_muted, length=2, width=0.5)
    if zero_center:
        vmin, vmax = image.get_clim()
        ticks = np.linspace(vmin, vmax, 5)
        colorbar.set_ticks(ticks)
        colorbar.set_ticklabels(
            ["0%" if abs(t) < 1e-12 else f"{t * 100:+.0f}%" for t in ticks]
        )
        colorbar.ax.axhline(0.0, color=CONFIG.ui_text, linewidth=1.0)
    else:
        ticks = colorbar.get_ticks()
        colorbar.set_ticks(ticks)
        colorbar.set_ticklabels([f"{tick * 100:.0f}%" for tick in ticks])


def render_heatmaps(
    true_matrix: np.ndarray | None,
    pred_matrix: np.ndarray,
    display_threshold: float,
) -> Figure:
    """三联图：真实毁伤场 / 预测毁伤场（YlGnBu 单色调）/ 带符号误差场（RdBu_r 发散）。"""
    matrices_for_bounds = [pred_matrix]
    if true_matrix is not None:
        matrices_for_bounds.append(true_matrix)

    bounds = find_crop_bounds(
        matrices_for_bounds,
        threshold=display_threshold,
        margin=CONFIG.crop_margin,
    )

    if true_matrix is None:
        figure = Figure(figsize=(8.8, 6.4), dpi=100, constrained_layout=True)
        figure.patch.set_facecolor(CONFIG.ui_bg)
        axis = figure.add_subplot(1, 1, 1)
        axis.set_anchor("C")
        cropped, extent = crop_matrix_and_extent(pred_matrix, bounds)
        image = axis.imshow(
            cropped, extent=extent, origin="lower", cmap=DAMAGE_CMAP,
            vmin=0.0, vmax=1.0, aspect="equal",
        )
        _style_heatmap_axis(axis, "预测毁伤场 Predicted")
        _add_percent_colorbar(figure, image, axis, "毁伤强度")
        return figure

    figure = Figure(figsize=(12.8, 4.6), dpi=100, constrained_layout=True)
    figure.patch.set_facecolor(CONFIG.ui_bg)
    axes = [figure.add_subplot(1, 3, i + 1) for i in range(3)]

    for index, (axis, (title, matrix)) in enumerate(zip(
        axes[:2],
        [("真实毁伤场 True", true_matrix), ("预测毁伤场 Predicted", pred_matrix)],
    )):
        cropped, extent = crop_matrix_and_extent(matrix, bounds)
        image = axis.imshow(
            cropped, extent=extent, origin="lower", cmap=DAMAGE_CMAP,
            vmin=0.0, vmax=1.0, aspect="equal",
        )
        _style_heatmap_axis(axis, title, show_y_axis=(index == 0))
        _add_percent_colorbar(figure, image, axis, "毁伤强度")

    signed_error = pred_matrix.astype(np.float32) - true_matrix.astype(np.float32)
    cropped_err, extent = crop_matrix_and_extent(signed_error, bounds)
    err_limit = max(float(np.nanmax(np.abs(cropped_err))), 0.10)
    image = axes[2].imshow(
        cropped_err, extent=extent, origin="lower", cmap=ERROR_CMAP,
        vmin=-err_limit, vmax=err_limit, aspect="equal",
    )
    _style_heatmap_axis(axes[2], "误差 (预测 − 真实)", show_y_axis=False)
    _add_percent_colorbar(figure, image, axes[2], "误差", zero_center=True)

    return figure


def render_full_prediction(pred_matrix: np.ndarray) -> Figure:
    """全视图预测图：显示整个 ROI 范围内的预测毁伤场。"""
    roi = roi_mask_for_shape(pred_matrix.shape)
    rows = np.flatnonzero(roi.any(axis=1))
    cols = np.flatnonzero(roi.any(axis=0))
    bounds = (int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)

    figure = Figure(figsize=(7.6, 6.6), dpi=100, constrained_layout=True)
    figure.patch.set_facecolor(CONFIG.ui_bg)
    axis = figure.add_subplot(1, 1, 1)
    # 单张大图水平居中：固定纵横比的图像在画布拉伸时锚定中心而非左侧
    axis.set_anchor("C")
    cropped, extent = crop_matrix_and_extent(pred_matrix, bounds)
    image = axis.imshow(
        cropped, extent=extent, origin="lower", cmap=DAMAGE_CMAP,
        vmin=0.0, vmax=1.0, aspect="equal",
    )
    _style_heatmap_axis(axis, "全视图预测毁伤场（完整 ROI）")
    _add_percent_colorbar(figure, image, axis, "毁伤强度")
    return figure


def _rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs,
) -> int:
    """在 Canvas 上绘制圆角矩形（smooth polygon 近似）。"""
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class DamagePredictionGUI:
    # 工况输入的合法范围与 Spinbox 步长：(下限, 上限, 步长)。
    # 箭头微调受 from_/to 约束，手动键入在 _current_condition 中二次校验，
    # 防止非法字符或极端负数进入后端插值器导致崩溃。
    CONDITION_LIMITS: dict[str, tuple[float, float, float]] = {
        "h": (0.0, 500.0, 5.0),
        "v": (0.0, 1000.0, 10.0),
        "deg": (0.0, 90.0, 1.0),
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1600x920")
        self.root.minsize(1280, 780)

        self.data_dir_var = tk.StringVar(value=str(app_base_dir() / "data"))
        self.level_var = tk.StringVar(value="F")
        self.h_var = tk.StringVar(value="0.0")
        self.v_var = tk.StringVar(value="150.0")
        self.deg_var = tk.StringVar(value="20.0")
        self.status_var = tk.StringVar(value="请选择数据目录并训练模型。")

        self.bundle: ModelBundle | None = None
        self.service: DamageModelService | None = None
        self.current_prediction: np.ndarray | None = None
        self.current_truth: np.ndarray | None = None
        self.current_figure: Figure | None = None
        self.current_condition: Condition | None = None

        # 瞄准优化参数状态 (TASK 005)
        self.spread_mode_var = tk.StringVar(value="CEP")
        self.cep_var = tk.StringVar(value="5.0")
        self.rep_var = tk.StringVar(value="2.0")
        self.dep_var = tk.StringVar(value="2.0")
        self.current_aim_result: AimOptimizationResult | None = None
        self.current_value_field: np.ndarray | None = None

        # 结果区双标签页画布与动画状态
        self.figures: dict[str, Figure | None] = {"triple": None, "full": None, "aim": None}
        self.canvases: dict[str, FigureCanvasTkAgg | None] = {"triple": None, "full": None, "aim": None}
        self._busy_animating = False
        self._anim_phase = 0
        self._syncing_fields = False

        self._apply_window_icon()
        self._configure_styles()
        self._build_layout()
        self._set_data_dir(self.data_dir_var.get())

    def _apply_window_icon(self) -> None:
        ico_path, png_path = resolve_icon_paths()
        try:
            if ico_path is not None:
                self.root.iconbitmap(default=str(ico_path))
        except tk.TclError:
            pass
        try:
            if png_path is not None:
                icon_image = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, icon_image)
                self._icon_image = icon_image
            else:
                self._icon_image = None
        except tk.TclError:
            self._icon_image = None

    def _configure_styles(self) -> None:
        self.root.configure(bg=CONFIG.ui_bg)
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = ("Microsoft YaHei", 10)
        title_font = ("Microsoft YaHei", 12, "bold")
        hero_font = ("Microsoft YaHei", 18, "bold")
        small_font = ("Microsoft YaHei", 9)

        style.configure(".", font=default_font)
        style.configure("App.TFrame", background=CONFIG.ui_bg)
        style.configure("Card.TFrame", background=CONFIG.ui_panel_bg, relief="flat")
        style.configure("Soft.TFrame", background=CONFIG.ui_soft_bg, relief="flat")
        style.configure(
            "Title.TLabel",
            background=CONFIG.ui_bg,
            foreground=CONFIG.ui_text,
            font=hero_font,
        )
        style.configure(
            "Subtitle.TLabel",
            background=CONFIG.ui_bg,
            foreground=CONFIG.ui_muted,
            font=small_font,
        )
        style.configure(
            "CardTitle.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_text,
            font=title_font,
        )
        style.configure(
            "CardText.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_muted,
            font=small_font,
        )
        style.configure(
            "Section.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_primary,
            font=("Microsoft YaHei", 10, "bold"),
        )
        style.configure(
            "SoftSection.TLabel",
            background=CONFIG.ui_soft_bg,
            foreground=CONFIG.ui_primary,
            font=("Microsoft YaHei", 10, "bold"),
        )
        style.configure(
            "FieldLabel.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9),
        )
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=CONFIG.ui_soft_bg,
            background=CONFIG.ui_accent,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_accent,
            darkcolor=CONFIG.ui_accent,
            thickness=8,
        )
        style.configure(
            "App.TNotebook",
            background=CONFIG.ui_bg,
            borderwidth=0,
            tabmargins=(0, 0, 0, 6),
        )
        style.configure(
            "App.TNotebook.Tab",
            font=("Microsoft YaHei", 9),
            padding=(18, 6),
            background=CONFIG.ui_bg,
            foreground=CONFIG.ui_muted,
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", CONFIG.ui_primary)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.configure(
            "Accent.TButton",
            font=("Microsoft YaHei", 10),
            padding=(10, 10),
            background=CONFIG.ui_primary,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", CONFIG.ui_primary_dark),
                ("pressed", CONFIG.ui_primary_dark),
                ("disabled", "#9FAFD6"),
            ],
            foreground=[("disabled", "#F1F4FA"), ("!disabled", "#FFFFFF")],
        )
        style.configure(
            "Ghost.TButton",
            font=("Microsoft YaHei", 9),
            padding=(10, 7),
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_primary,
            bordercolor=CONFIG.ui_primary,
            lightcolor=CONFIG.ui_panel_bg,
            darkcolor=CONFIG.ui_panel_bg,
            borderwidth=1,
            focusthickness=0,
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#EFF4FB"), ("pressed", "#E4ECF7")],
        )
        style.configure(
            "Primary.TButton",
            font=("Microsoft YaHei", 10),
            padding=(10, 9),
            background=CONFIG.ui_primary,
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", CONFIG.ui_primary_dark), ("pressed", CONFIG.ui_primary_dark)],
            foreground=[("disabled", "#dfe7ed"), ("!disabled", "#ffffff")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Microsoft YaHei", 10),
            padding=(10, 8),
            background=CONFIG.ui_soft_bg,
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_soft_bg,
            darkcolor=CONFIG.ui_soft_bg,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#e6edf2"), ("pressed", "#dce5eb")],
        )
        style.configure(
            "App.TEntry",
            fieldbackground="#FFFFFF",
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_border,
            darkcolor=CONFIG.ui_border,
            padding=6,
        )
        style.configure(
            "App.TSpinbox",
            fieldbackground="#FFFFFF",
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_border,
            darkcolor=CONFIG.ui_border,
            arrowcolor=CONFIG.ui_primary,
            arrowsize=12,
            padding=6,
        )
        style.configure(
            "App.TCombobox",
            fieldbackground="#FFFFFF",
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_border,
            darkcolor=CONFIG.ui_border,
            padding=5,
        )
        style.configure(
            "Line.TSeparator",
            background=CONFIG.ui_border,
        )

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()

        body = ttk.Frame(self.root, style="App.TFrame", padding=(18, 14, 18, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0, minsize=320)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

        self._update_key_metrics(None, None)
        self._update_summary_card(None)
        self._update_detail_card()
        self._update_advice_card(None, None, "")

    # ---------- 顶部标题栏 ----------

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=CONFIG.ui_header_bg)
        header.grid(row=0, column=0, sticky="ew")
        inner = tk.Frame(header, bg=CONFIG.ui_header_bg)
        inner.pack(fill="x", padx=20, pady=(7, 7))

        icon = tk.Canvas(
            inner, width=28, height=28, bg=CONFIG.ui_header_bg, highlightthickness=0
        )
        icon.pack(side="left", padx=(0, 10))
        self._draw_header_icon(icon)

        # 顶部保持纯净：模型类型与指标信息在底部卡片中已有体现，此处只保留标题
        tk.Label(
            inner,
            text="基于数据驱动的毁伤效能快速评估",
            bg=CONFIG.ui_header_bg,
            fg=CONFIG.ui_header_fg,
            font=("Microsoft YaHei", 13),
        ).pack(side="left")

    @staticmethod
    def _draw_header_icon(canvas: tk.Canvas) -> None:
        """扁平应用图标：高亮圆角方块 + 导弹剪影 + 数据点。"""
        _rounded_rect(canvas, 1, 1, 27, 27, 7, fill="#3B5BC0", outline="")
        canvas.create_polygon(14, 5, 17.5, 13, 10.5, 13, fill="#FFFFFF", outline="")
        canvas.create_rectangle(12.5, 13, 15.5, 19, fill="#FFFFFF", outline="")
        for cx, cy in ((9, 22), (14, 23.5), (19, 22)):
            canvas.create_oval(cx - 1.4, cy - 1.4, cx + 1.4, cy + 1.4, fill="#B6C3E4", outline="")

    # ---------- 圆角卡片工厂 ----------

    def _make_card(
        self,
        parent: tk.Misc,
        title: str | None = None,
        soft: bool = False,
    ) -> tuple[tk.Canvas, tk.Frame, str]:
        """创建圆角+微阴影的信息卡片（Canvas 绘制），返回 (外框, 内容容器, 背景色)。"""
        bg = CONFIG.ui_panel_bg
        pad_x, pad_y = 16, 13
        holder = tk.Canvas(parent, bg=CONFIG.ui_bg, highlightthickness=0, bd=0)
        content = tk.Frame(holder, bg=bg)
        window_id = holder.create_window(pad_x, pad_y, window=content, anchor="nw")

        def redraw(_event: object = None) -> None:
            width = holder.winfo_width()
            if width <= 1:
                return
            holder.itemconfigure(window_id, width=max(width - 2 * pad_x - 3, 10))
            wanted = content.winfo_reqheight() + 2 * pad_y + 3
            if int(holder.cget("height")) != wanted:
                holder.configure(height=wanted)
            height = max(holder.winfo_height(), wanted)
            holder.delete("cardbg")
            # 微弱阴影：向右下偏移 2px 的浅灰圆角矩形
            _rounded_rect(holder, 3, 4, width - 1, height - 1, 9,
                          fill=CONFIG.ui_shadow, outline="", tags="cardbg")
            _rounded_rect(holder, 0, 0, width - 3, height - 4, 8,
                          fill=bg, outline="", tags="cardbg")
            holder.tag_lower("cardbg")

        holder.bind("<Configure>", redraw)
        content.bind("<Configure>", redraw)
        if title:
            # 统一对齐基准：卡片标题一律加粗、靠左上
            tk.Label(
                content, text=title, bg=bg, fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 9, "bold"),
            ).pack(anchor="nw", pady=(0, 8))
        return holder, content, bg

    # ---------- 左侧：参数配置（可滚动） ----------

    def _build_left_panel(self, body: ttk.Frame) -> None:
        # Canvas + Scrollbar 实现左侧可滚动容器
        container = ttk.Frame(body, style="App.TFrame")
        container.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)

        canvas = tk.Canvas(container, highlightthickness=0, bg=CONFIG.ui_bg)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 内部 Frame 承载所有卡片
        left = ttk.Frame(canvas, style="App.TFrame")
        left.columnconfigure(0, weight=1)
        self._left_canvas_window = canvas.create_window((0, 0), window=left, anchor="nw")

        # 内容变化时更新 scrollregion
        def _on_left_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 确保内部 frame 宽度与 canvas 一致（水平不滚动）
            canvas.itemconfig(self._left_canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_left_configure)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            # Windows: event.delta 通常为 ±120 的倍数
            canvas.yview_scroll(int(-event.delta / 120), "units")

        def _on_enter(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _on_leave(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _on_enter)
        canvas.bind("<Leave>", _on_leave)

        self._left_canvas = canvas

        card, box, bg = self._make_card(left, "模型操作")
        card.grid(row=0, column=0, sticky="ew")
        tk.Label(box, text="数据目录", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(anchor="w")
        # 路径选择器紧凑化：输入框与浏览按钮横向并排，节省纵向空间
        dir_row = tk.Frame(box, bg=bg)
        dir_row.pack(fill="x", pady=(4, 0))
        ttk.Entry(dir_row, textvariable=self.data_dir_var, style="App.TEntry").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            dir_row, text="浏览…", command=self.on_browse_data,
            style="Ghost.TButton", width=6,
        ).pack(side="left", padx=(6, 0))
        tk.Label(box, text="毁伤等级", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(14, 0))
        ttk.Combobox(
            box,
            textvariable=self.level_var,
            values=["F", "M", "P"],
            state="readonly",
            style="App.TCombobox",
        ).pack(fill="x", pady=(4, 0))

        # 模型操作为低频配置操作，统一使用次要按钮样式（白底蓝边 / 浅灰底），
        # 视觉权重让位于高频核心操作"开始预测"（Accent 深蓝高亮）。
        buttons = tk.Frame(box, bg=bg)
        buttons.pack(fill="x", pady=(16, 0))
        buttons.columnconfigure((0, 1), weight=1)
        self.train_button = ttk.Button(buttons, text="训练模型", command=self.on_train, style="Ghost.TButton")
        self.train_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.save_button = ttk.Button(buttons, text="保存模型", command=self.on_save_model, style="Secondary.TButton")
        self.save_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.load_button = ttk.Button(box, text="加载模型...", command=self.on_load_model, style="Secondary.TButton")
        self.load_button.pack(fill="x", pady=(10, 0))

        card2, box2, bg2 = self._make_card(left, "工况输入")
        card2.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        for icon, label, variable, key in (
            ("⛰", "高度 h (m)", self.h_var, "h"),
            ("➤", "速度 v (m/s)", self.v_var, "v"),
            ("∠", "角度 deg (°)", self.deg_var, "deg"),
        ):
            lo, hi, step = self.CONDITION_LIMITS[key]
            self._build_condition_field(box2, bg2, icon, label, variable, lo, hi, step)

        self.predict_button = ttk.Button(box2, text="开始预测", command=self.on_predict, style="Accent.TButton")
        self.predict_button.pack(fill="x", pady=(14, 0))
        export_row = tk.Frame(box2, bg=bg2)
        export_row.pack(fill="x", pady=(10, 0))
        export_row.columnconfigure((0, 1), weight=1)
        ttk.Button(export_row, text="导出 CSV", command=self.on_export_csv, style="Ghost.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(export_row, text="导出 PNG", command=self.on_export_png, style="Ghost.TButton").grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # 瞄准优化卡片 (TASK 005)
        card3, box3, bg3 = self._make_card(left, "瞄准优化")
        card3.grid(row=2, column=0, sticky="ew", pady=(14, 0))

        tk.Label(box3, text="散布模式", bg=bg3, fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 9)).pack(anchor="w")
        mode_row = tk.Frame(box3, bg=bg3)
        mode_row.pack(fill="x", pady=(4, 0))

        def _on_spread_mode_change(*_args):
            mode = self.spread_mode_var.get()
            if mode == "CEP":
                self._aim_cep_frame.pack(fill="x", pady=(10, 0))
                self._aim_rep_dep_frame.pack_forget()
            else:
                self._aim_rep_dep_frame.pack(fill="x", pady=(10, 0))
                self._aim_cep_frame.pack_forget()

        ttk.Combobox(
            mode_row, textvariable=self.spread_mode_var,
            values=["CEP", "REP_DEP"], state="readonly",
            style="App.TCombobox",
        ).pack(fill="x")
        self.spread_mode_var.trace_add("write", _on_spread_mode_change)

        # CEP 输入
        self._aim_cep_frame = tk.Frame(box3, bg=bg3)
        self._aim_cep_frame.pack(fill="x", pady=(10, 0))
        tk.Label(self._aim_cep_frame, text="CEP (m)", bg=bg3, fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 9)).pack(anchor="w")
        ttk.Entry(self._aim_cep_frame, textvariable=self.cep_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))

        # REP/DEP 输入
        self._aim_rep_dep_frame = tk.Frame(box3, bg=bg3)
        tk.Label(self._aim_rep_dep_frame, text="REP (m)", bg=bg3, fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 9)).pack(anchor="w")
        ttk.Entry(self._aim_rep_dep_frame, textvariable=self.rep_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))
        tk.Label(self._aim_rep_dep_frame, text="DEP (m)", bg=bg3, fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(8, 0))
        ttk.Entry(self._aim_rep_dep_frame, textvariable=self.dep_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))

        self.optimize_button = ttk.Button(
            box3, text="计算最佳瞄准点", command=self.on_optimize_aim,
            style="Accent.TButton",
        )
        self.optimize_button.pack(fill="x", pady=(14, 0))

    def _build_condition_field(
        self,
        parent: tk.Frame,
        bg: str,
        icon: str,
        label: str,
        variable: tk.StringVar,
        from_: float,
        to: float,
        increment: float,
    ) -> None:
        """带小图标的现代化输入字段（Spinbox 微调器，限制数值范围防误输入）。"""
        field = tk.Frame(parent, bg=bg)
        field.pack(fill="x", pady=(0, 12))
        head = tk.Frame(field, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=icon, bg=bg, fg=CONFIG.ui_primary, font=("Microsoft YaHei", 10)).pack(side="left")
        tk.Label(head, text=f" {label}", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(side="left")
        ttk.Spinbox(
            field,
            textvariable=variable,
            from_=from_,
            to=to,
            increment=increment,
            style="App.TSpinbox",
            font=("Microsoft YaHei", 11),
        ).pack(fill="x", pady=(5, 0))

    # ---------- 右侧：核心展示区 ----------

    def _build_right_panel(self, body: ttk.Frame) -> None:
        right = ttk.Frame(body, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        tk.Label(
            right,
            text="流程：选择数据目录与等级 → 训练或加载模型 → 输入工况开始预测 → 查看热力图与指标 → 导出结果",
            bg=CONFIG.ui_bg,
            fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.result_tabs = ttk.Notebook(right, style="App.TNotebook")
        self.result_tabs.grid(row=1, column=0, sticky="nsew")
        self.tab_frames: dict[str, tk.Frame] = {}
        for key, label in (("triple", "对比三联图"), ("full", "全视图预测图"), ("aim", "瞄准优化")):
            frame = tk.Frame(self.result_tabs, bg=CONFIG.ui_bg)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            self.result_tabs.add(frame, text=f"  {label}  ")
            self.tab_frames[key] = frame
            tk.Label(
                frame,
                text="训练模型并执行预测后，此处显示毁伤热力图",
                bg=CONFIG.ui_bg,
                fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 10),
            ).grid(row=0, column=0)
        # 画布在隐藏标签页里创建时拿不到真实尺寸，切换显示会残留错误布局
        # （单张大图向右偏移）；切换标签页时按当前尺寸强制重排并重绘。
        self.result_tabs.bind("<<NotebookTabChanged>>", self._on_result_tab_changed)

        report = ttk.Frame(right, style="App.TFrame")
        report.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        report.columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="report")

        # 运行状态卡（与指标卡并排的微型仪表盘）：核心状态字居中放大突出
        card0, box0, bg0 = self._make_card(report, "运行状态")
        card0.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        state_row = tk.Frame(box0, bg=bg0)
        state_row.pack(pady=(2, 0))
        self.status_dot = tk.Label(state_row, text="●", bg=bg0, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 11))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.state_label = tk.Label(state_row, text="就绪", bg=bg0, fg=CONFIG.ui_text, font=("Microsoft YaHei", 18, "bold"))
        self.state_label.pack(side="left")
        progress_row = tk.Frame(box0, bg=bg0)
        progress_row.pack(fill="x", pady=(8, 0))
        self.progress_percent = tk.Label(progress_row, text="0%", bg=bg0, fg=CONFIG.ui_primary, font=("Microsoft YaHei", 9), width=4, anchor="e")
        self.progress_percent.pack(side="right", padx=(4, 0))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            progress_row,
            variable=self.progress_var,
            maximum=100.0,
            style="App.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, pady=3)
        self.stage_label = tk.Label(
            box0, text="等待任务...", bg=bg0, fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9), anchor="w", justify="left",
        )
        self.stage_label.pack(anchor="w", pady=(4, 0), fill="x")
        self._bind_autowrap(self.stage_label)
        self.status_message = tk.Label(
            box0, text="请选择数据目录并训练模型。", bg=bg0, fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9), anchor="w", justify="left",
        )
        self.status_message.pack(anchor="w", pady=(4, 0), fill="x")
        self._bind_autowrap(self.status_message)

        # 关键指标卡：核心大字指标在卡片正中放大突出
        card, box, bg = self._make_card(report, "关键指标报告")
        card.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self.p95_value = tk.Label(box, text="--", bg=bg, fg=CONFIG.ui_text, font=("Microsoft YaHei", 22, "bold"))
        self.p95_value.pack(pady=(2, 0))
        self.p95_status = tk.Label(box, text="P95 混合误差", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9))
        self.p95_status.pack()
        self.meanre_value = tk.Label(box, text="--", bg=bg, fg=CONFIG.ui_text, font=("Microsoft YaHei", 14, "bold"))
        self.meanre_value.pack(pady=(10, 0))
        self.meanre_status = tk.Label(box, text="平均相对误差", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9))
        self.meanre_status.pack()

        card2, box2, bg2 = self._make_card(report, "输入配置摘要")
        card2.grid(row=0, column=2, sticky="nsew", padx=(0, 10))
        self.summary_label = tk.Label(
            box2, text="--", bg=bg2, fg=CONFIG.ui_text, font=("Microsoft YaHei", 9),
            justify="left", anchor="nw",
        )
        self.summary_label.pack(anchor="w", fill="both", expand=True)
        self._bind_autowrap(self.summary_label)

        card3, box3, bg3 = self._make_card(report, "模型细节")
        card3.grid(row=0, column=3, sticky="nsew", padx=(0, 10))
        self.detail_label = tk.Label(
            box3, text="--", bg=bg3, fg=CONFIG.ui_text, font=("Microsoft YaHei", 9),
            justify="left", anchor="nw",
        )
        self.detail_label.pack(anchor="w", fill="both", expand=True)
        self._bind_autowrap(self.detail_label)

        card4, box4, bg4 = self._make_card(report, "建议")
        card4.grid(row=0, column=4, sticky="nsew")
        self.advice_label = tk.Label(
            box4, text="--", bg=bg4, fg=CONFIG.ui_text, font=("Microsoft YaHei", 9),
            justify="left", anchor="nw",
        )
        self.advice_label.pack(anchor="w", fill="both", expand=True)
        self._bind_autowrap(self.advice_label)

    @staticmethod
    def _bind_autowrap(label: tk.Label, min_width: int = 80) -> None:
        """让 Label 的换行宽度跟随实际可用宽度，避免固定 wraplength 截断长文本。"""
        def on_configure(event: "tk.Event[tk.Label]") -> None:
            label.configure(wraplength=max(event.width - 8, min_width))

        label.bind("<Configure>", on_configure)

    def _selected_result_tab_key(self) -> str:
        """返回当前选中的结果标签页 key（triple / full / aim）。"""
        selected = self.result_tabs.select()
        for key, frame in self.tab_frames.items():
            if selected == str(frame):
                return key
        return "triple"

    def _on_result_tab_changed(self, _event: object = None) -> None:
        """切换结果标签页时按当前真实尺寸重绘画布，修复隐藏期创建导致的偏移。"""
        which = self._selected_result_tab_key()
        canvas = self.canvases.get(which)
        if canvas is None:
            return
        self.root.update_idletasks()
        widget = canvas.get_tk_widget()
        width, height = widget.winfo_width(), widget.winfo_height()
        if width > 1 and height > 1:
            # 与 FigureCanvasTkAgg.resize 相同的逻辑：把画布尺寸同步给 Figure
            dpi = canvas.figure.dpi
            canvas.figure.set_size_inches(width / dpi, height / dpi, forward=False)
        canvas.draw_idle()

    def _set_status(self, text: str, kind: str = "info") -> None:
        self.status_var.set(text)
        if hasattr(self, "status_message"):
            self.status_message.configure(text=text)
        colors = {
            "info": CONFIG.ui_muted,
            "busy": CONFIG.ui_busy,
            "ok": CONFIG.ui_success,
            "error": CONFIG.ui_danger,
        }
        states = {"info": "就绪", "busy": "运行中", "ok": "已完成", "error": "出错"}
        if hasattr(self, "status_dot"):
            self.status_dot.configure(fg=colors.get(kind, CONFIG.ui_muted))
        if hasattr(self, "state_label"):
            self.state_label.configure(
                text=states.get(kind, "就绪"), fg=colors.get(kind, CONFIG.ui_text)
            )
        self._set_animating(kind == "busy")
        self.root.update_idletasks()

    def _set_animating(self, active: bool) -> None:
        """运行状态点的呼吸灯效果：busy 时启动，其余状态自动停止。"""
        if active and not self._busy_animating:
            self._busy_animating = True
            self._animate_status_dot()
        elif not active:
            self._busy_animating = False

    def _animate_status_dot(self) -> None:
        if not self._busy_animating:
            return
        pulse_colors = ("#e8b45a", CONFIG.ui_busy, "#c98f2f", CONFIG.ui_busy)
        self._anim_phase = (self._anim_phase + 1) % len(pulse_colors)
        try:
            self.status_dot.configure(fg=pulse_colors[self._anim_phase])
            self.root.after(300, self._animate_status_dot)
        except tk.TclError:
            self._busy_animating = False

    def _set_progress(self, percent: float, stage: str) -> None:
        self.progress_var.set(percent)
        self.progress_percent.configure(text=f"{percent:.0f}%")
        self.stage_label.configure(text=stage)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for name in ("train_button", "predict_button", "save_button", "load_button", "optimize_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def _set_data_dir(self, data_dir: str) -> None:
        self.data_dir_var.set(data_dir)
        self.service = DamageModelService(DamageDataManager(data_dir))

    def _current_condition(self) -> Condition:
        try:
            values = {
                "h": float(self.h_var.get()),
                "v": float(self.v_var.get()),
                "deg": float(self.deg_var.get()),
            }
        except ValueError as exc:
            raise ValueError("h、v、deg 必须是数字") from exc

        for name, value in values.items():
            lo, hi, _step = self.CONDITION_LIMITS[name]
            if not (lo <= value <= hi):
                raise ValueError(f"{name} 超出合法范围 [{lo:g}, {hi:g}]，当前为 {value:g}")
        return Condition(**values)

    def _draw_figure(self, figure: Figure, which: str = "triple") -> None:
        self.figures[which] = figure
        self.current_figure = figure
        frame = self.tab_frames[which]
        old_canvas = self.canvases.get(which)
        if old_canvas is not None:
            old_canvas.get_tk_widget().destroy()
        for child in frame.winfo_children():
            if isinstance(child, tk.Label):
                child.destroy()
        canvas = FigureCanvasTkAgg(figure, master=frame)
        widget = canvas.get_tk_widget()
        widget.configure(bg=CONFIG.ui_bg, highlightthickness=0, bd=0)
        widget.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        canvas.draw()
        self.canvases[which] = canvas

    # ---------- 报告卡片更新 ----------

    def _metric_display(
        self, value: float | None, label: str
    ) -> tuple[str, str, str, str]:
        target = CONFIG.relative_error_target
        if value is None or pd.isna(value):
            return "--", CONFIG.ui_text, f"{label} · 目标 < {target:.0%}", CONFIG.ui_muted
        if value < target:
            return (
                f"{value:.2%}", CONFIG.ui_success,
                f"{label} · 通过目标 < {target:.0%} ✔", CONFIG.ui_success,
            )
        return (
            f"{value:.2%}", CONFIG.ui_danger,
            f"{label} · 未达目标 < {target:.0%} ✘", CONFIG.ui_danger,
        )

    def _update_key_metrics(
        self, mean_re: float | None, p95_hybrid: float | None
    ) -> None:
        value, value_color, status, status_color = self._metric_display(p95_hybrid, "P95 混合误差")
        self.p95_value.configure(text=value, fg=value_color)
        self.p95_status.configure(text=status, fg=status_color)
        value, value_color, status, status_color = self._metric_display(mean_re, "平均相对误差")
        self.meanre_value.configure(text=value, fg=value_color)
        self.meanre_status.configure(text=status, fg=status_color)

    @staticmethod
    def _short_path(path: str, limit: int = 36) -> str:
        return path if len(path) <= limit else "…" + path[-(limit - 1):]

    def _update_summary_card(self, condition: Condition | None) -> None:
        lines = [
            f"数据路径: {self._short_path(self.data_dir_var.get())}",
            f"毁伤等级: {self.level_var.get()}",
        ]
        if condition is not None:
            lines.append(
                f"工况: h={condition.h:g} m, v={condition.v:g} m/s, deg={condition.deg:g}°"
            )
        else:
            lines.append("工况: 尚未预测")
        self.summary_label.configure(text="\n".join(lines))

    def _update_detail_card(self) -> None:
        if self.bundle is None:
            self.detail_label.configure(text="尚未训练或加载模型。")
            return
        self.detail_label.configure(
            text=(
                f"训练集: {len(self.bundle.train_conditions)} 工况\n"
                f"测试集: {len(self.bundle.test_conditions)} 工况\n"
                f"RBF 核: {CONFIG.rbf_kernel}\n"
                f"质心对齐: {'开启' if CONFIG.align_patterns else '关闭'}\n"
                f"降噪: 双边滤波 σs={CONFIG.denoise_sigma_spatial:g}\n"
                f"评估口径: σ={CONFIG.eval_smoothing_sigma:g} 局部平均场"
            )
        )

    def _update_advice_card(
        self, mean_re: float | None, p95_hybrid: float | None, scope: str
    ) -> None:
        target = CONFIG.relative_error_target
        if mean_re is None or pd.isna(mean_re):
            text = "训练或预测完成后，此处将给出结论与建议。"
        elif mean_re < target and p95_hybrid is not None and p95_hybrid < target:
            text = (
                f"{scope}核心指标全部达标（目标 <{target:.0%}）。"
                "预测模型符合精度要求，可以用于后续毁伤效能评估，建议导出结果文件存档。"
            )
        elif mean_re < target:
            text = (
                f"{scope}平均精度达标，但 P95 混合误差超标，说明存在局部误差偏大的区域。"
                "建议切换到误差图定位偏差位置，或在该工况附近加密仿真数据后重新训练。"
            )
        else:
            text = (
                f"{scope}核心指标未达标。建议确认数据目录完整、"
                "加密训练工况网格（尤其大角度/低速角落区域）后重新训练。"
            )
        self.advice_label.configure(text=text)

    def on_browse_data(self) -> None:
        selected = filedialog.askdirectory(
            title="选择 data 文件夹",
            initialdir=self.data_dir_var.get(),
        )
        if not selected:
            return
        self._set_data_dir(selected)
        self._set_status(f"已选择数据目录: {selected}")

    def on_train(self) -> None:
        try:
            if self.service is None:
                raise RuntimeError("数据服务未初始化")

            level = self.level_var.get().strip().upper()
            self._set_busy(True)
            self._set_status(f"正在训练等级 {level} 模型（读取矩阵并拟合插值场），请稍候...", kind="busy")

            def report_progress(done: int, total: int, stage: str) -> None:
                percent = done / total * 100.0 if total > 0 else 0.0
                self._set_progress(percent, stage)
                self.root.update()

            bundle = self.service.train_bundle(level, progress=report_progress)
            self.bundle = bundle
            self._set_progress(100.0, "训练与评估完成")

            accuracy_path = app_base_dir() / f"gui_accuracy_report_{level}.csv"
            condition_path = app_base_dir() / f"gui_condition_report_{level}.csv"
            bundle.accuracy_report.to_csv(accuracy_path, index=False, encoding="utf-8-sig")
            bundle.condition_report.to_csv(condition_path, index=False, encoding="utf-8-sig")

            focus_scope = f"damage_gt_{CONFIG.relative_error_threshold:.2f}"
            focus = bundle.accuracy_report[bundle.accuracy_report["scope"] == focus_scope]
            mean_re: float | None = None
            p95_hybrid: float | None = None
            core_summary = ""
            if not focus.empty and not pd.isna(focus.iloc[0]["MeanRelativeError"]):
                mean_re = float(focus.iloc[0]["MeanRelativeError"])
                p95_hybrid = float(focus.iloc[0]["P95HybridError"])
                core_summary = (
                    f"核心指标: 平均相对误差 {mean_re:.2%}, "
                    f"P95混合误差 {p95_hybrid:.2%} "
                    f"(目标 <{CONFIG.relative_error_target:.0%})。"
                )
            self._update_key_metrics(mean_re, p95_hybrid)
            self._update_summary_card(self.current_condition)
            self._update_detail_card()
            self._update_advice_card(mean_re, p95_hybrid, "测试集")
            self._set_status(
                f"训练完成: {level}。{core_summary}"
                f"评估结果已保存为 {accuracy_path.name} 和 {condition_path.name}",
                kind="ok",
            )
        except Exception as exc:
            self._handle_error("训练失败", exc)
        finally:
            self._set_busy(False)
            if hasattr(self, "progress_var"):
                self._set_progress(0.0, "等待任务...")

    def on_save_model(self) -> None:
        try:
            if self.bundle is None:
                raise RuntimeError("请先训练或加载模型")
            output_path = filedialog.asksaveasfilename(
                title="保存模型",
                defaultextension=".joblib",
                filetypes=[("Joblib Model", "*.joblib")],
                initialfile=f"damage_model_{self.bundle.level}.joblib",
            )
            if not output_path:
                return
            joblib.dump(self.bundle, output_path)
            self._set_status(f"模型已保存: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("保存模型失败", exc)

    def on_load_model(self) -> None:
        try:
            model_path = filedialog.askopenfilename(
                title="加载模型",
                filetypes=[("Joblib Model", "*.joblib")],
            )
            if not model_path:
                return
            bundle = joblib.load(model_path)
            if not isinstance(bundle, ModelBundle):
                raise TypeError("模型文件格式不正确")
            self.bundle = bundle
            self.level_var.set(bundle.level)
            if bundle.data_dir:
                self._set_data_dir(bundle.data_dir)

            mean_re: float | None = None
            p95_hybrid: float | None = None
            if not bundle.accuracy_report.empty:
                focus_scope = f"damage_gt_{CONFIG.relative_error_threshold:.2f}"
                focus = bundle.accuracy_report[bundle.accuracy_report["scope"] == focus_scope]
                if not focus.empty and not pd.isna(focus.iloc[0]["MeanRelativeError"]):
                    mean_re = float(focus.iloc[0]["MeanRelativeError"])
                    p95_hybrid = float(focus.iloc[0]["P95HybridError"])
            self._update_key_metrics(mean_re, p95_hybrid)
            self._update_summary_card(self.current_condition)
            self._update_detail_card()
            self._update_advice_card(mean_re, p95_hybrid, "测试集")
            self._set_status(f"模型已加载: {model_path}", kind="ok")
        except Exception as exc:
            self._handle_error("加载模型失败", exc)

    def on_predict(self) -> None:
        try:
            if self.bundle is None:
                raise RuntimeError("请先训练或加载模型")
            if self.service is None:
                raise RuntimeError("数据服务未初始化")

            condition = self._current_condition()
            self.current_condition = condition
            self._set_status("正在预测并生成热力图...", kind="busy")
            self.current_prediction = self.service.predict_matrix(self.bundle, condition)
            self.current_truth = None

            # 新预测后清空旧瞄准优化结果 (TASK 005)
            self.current_aim_result = None
            self.current_value_field = None
            self._clear_aim_view()

            record = None
            try:
                record = self.service.data_manager.find_record(self.bundle.level, condition)
            except Exception:
                record = None

            if record is not None:
                self.current_truth = read_damage_matrix(record.path)

            triple_figure = render_heatmaps(
                self.current_truth,
                self.current_prediction,
                display_threshold=CONFIG.display_threshold,
            )
            self._draw_figure(triple_figure, which="triple")
            self._draw_figure(render_full_prediction(self.current_prediction), which="full")
            self.result_tabs.select(
                self.tab_frames["triple" if self.current_truth is not None else "full"]
            )
            self.current_figure = triple_figure

            self._update_summary_card(condition)
            self._update_detail_card()

            if self.current_truth is not None:
                eval_true, eval_pred = evaluation_fields(
                    self.current_truth, self.current_prediction
                )
                focus_mask = eval_true.ravel() > CONFIG.relative_error_threshold
                if np.any(focus_mask):
                    focus_metrics = metric_row(
                        f"damage_gt_{CONFIG.relative_error_threshold:.2f}",
                        eval_true.ravel()[focus_mask],
                        eval_pred.ravel()[focus_mask],
                        CONFIG.relative_error_threshold,
                    )
                    mean_re = float(focus_metrics["MeanRelativeError"])
                    p95_hybrid = float(focus_metrics["P95HybridError"])
                    self._update_key_metrics(mean_re, p95_hybrid)
                    self._update_advice_card(mean_re, p95_hybrid, "当前工况")
                else:
                    self._update_advice_card(None, None, "")
                    self.advice_label.configure(
                        text="当前工况无 damage>0.05 的毁伤区，相对误差指标不适用。"
                    )
                self._set_status(
                    "预测完成，并已匹配到真实矩阵，当前显示对比三联图。", kind="ok"
                )
            else:
                self.advice_label.configure(
                    text="当前工况在 data 中没有真实矩阵，展示全视图预测结果。"
                    "精度可参考关键指标卡片中训练时的测试集指标。"
                )
                self._set_status(
                    "预测完成，当前工况没有真实矩阵，显示全视图预测热力图。", kind="ok"
                )
        except Exception as exc:
            self._handle_error("预测失败", exc)

    def on_export_csv(self) -> None:
        try:
            if self.current_prediction is None or self.current_condition is None:
                raise RuntimeError("请先生成预测结果")
            output_path = filedialog.asksaveasfilename(
                title="导出预测矩阵 CSV",
                defaultextension=".csv",
                filetypes=[("CSV File", "*.csv")],
                initialfile=(
                    f"predicted_{self.bundle.level if self.bundle else 'X'}"
                    f"_h_{int(round(self.current_condition.h * 10))}"
                    f"_v_{int(round(self.current_condition.v * 10))}"
                    f"_deg_{int(round(self.current_condition.deg * 10))}.csv"
                ),
            )
            if not output_path:
                return

            x_axis, y_axis = coordinate_axes(self.current_prediction.shape)
            frame = pd.DataFrame(self.current_prediction, index=y_axis, columns=x_axis)
            frame.index.name = "y"
            frame.to_csv(output_path, encoding="utf-8-sig")
            self._set_status(f"预测矩阵已导出: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("导出 CSV 失败", exc)

    def on_export_png(self) -> None:
        try:
            which = self._selected_result_tab_key()
            figure = self.figures.get(which) or self.current_figure
            if figure is None:
                raise RuntimeError("请先生成热力图")
            self.current_figure = figure
            output_path = filedialog.asksaveasfilename(
                title="导出热力图 PNG",
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png")],
                initialfile="damage_heatmap.png",
            )
            if not output_path:
                return
            self.current_figure.savefig(output_path, dpi=CONFIG.export_dpi, bbox_inches="tight")
            self._set_status(f"热力图已导出: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("导出 PNG 失败", exc)

    # ---------- 瞄准优化 (TASK 005) ----------

    def _clear_aim_view(self) -> None:
        """清空瞄准优化标签页内容。"""
        frame = self.tab_frames.get("aim")
        if frame is None:
            return
        old_canvas = self.canvases.get("aim")
        if old_canvas is not None:
            old_canvas.get_tk_widget().destroy()
            self.canvases["aim"] = None
        for child in frame.winfo_children():
            child.destroy()
        self.figures["aim"] = None
        tk.Label(
            frame, text="预测完成后，输入散布参数并点击「计算最佳瞄准点」",
            bg=CONFIG.ui_bg, fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 10),
        ).grid(row=0, column=0)

    def on_optimize_aim(self) -> None:
        """计算最佳瞄准点。"""
        try:
            if self.current_prediction is None:
                raise RuntimeError("请先执行毁伤场预测")

            x_axis, y_axis = coordinate_axes(self.current_prediction.shape)

            mode = self.spread_mode_var.get()
            if mode == "CEP":
                cep_val = float(self.cep_var.get())
                if cep_val < 0:
                    raise ValueError("CEP 必须非负")
                result = optimize_aim(
                    self.current_prediction, x_axis, y_axis,
                    spread_mode="CEP", cep=cep_val, reliability=1.0,
                )
            else:
                rep_val = float(self.rep_var.get())
                dep_val = float(self.dep_var.get())
                result = optimize_aim(
                    self.current_prediction, x_axis, y_axis,
                    spread_mode="REP_DEP", rep=rep_val, dep=dep_val, reliability=1.0,
                )

            self.current_aim_result = result
            self.current_value_field = result.value_field

            figure = self._render_aim_optimization(self.current_prediction, result)
            self._draw_figure(figure, which="aim")
            self._update_aim_summary(result)

            self.result_tabs.select(self.tab_frames["aim"])

            mode_label = f"CEP={self.cep_var.get()}m" if mode == "CEP" else \
                         f"REP={self.rep_var.get()}/DEP={self.dep_var.get()}m"
            self._set_status(
                f"瞄准优化完成 ({mode_label}): 最佳瞄准点 ({result.best_x:.1f}, {result.best_y:.1f}) m, "
                f"Vmax={result.vmax:.4f}, 增益={result.gain_relative:.2%}",
                kind="ok",
            )
        except Exception as exc:
            self._handle_error("瞄准优化失败", exc)

    def _render_aim_optimization(
        self,
        damage_matrix: np.ndarray,
        result: AimOptimizationResult,
    ) -> Figure:
        """渲染 D + V 双图：左图毁伤场，右图价值场，标记 D 峰值和最佳瞄准点。"""
        bounds = find_crop_bounds(
            [damage_matrix], threshold=CONFIG.display_threshold,
            margin=CONFIG.crop_margin,
        )

        figure = Figure(figsize=(12.8, 5.2), dpi=100, constrained_layout=True)
        figure.patch.set_facecolor(CONFIG.ui_bg)

        # 左图: 毁伤场 D
        ax0 = figure.add_subplot(1, 2, 1)
        cropped_d, extent_d = crop_matrix_and_extent(damage_matrix, bounds)
        im0 = ax0.imshow(
            cropped_d, extent=extent_d, origin="lower", cmap=DAMAGE_CMAP,
            vmin=0.0, vmax=1.0, aspect="equal",
        )
        _style_heatmap_axis(ax0, "毁伤场 D")
        _add_percent_colorbar(figure, im0, ax0, "毁伤值")

        # 右图: 价值场 V
        ax1 = figure.add_subplot(1, 2, 2)
        cropped_v, extent_v = crop_matrix_and_extent(result.value_field, bounds)
        vmax = max(float(result.value_field.max()), 1e-10)
        im1 = ax1.imshow(
            cropped_v, extent=extent_v, origin="lower", cmap="viridis",
            vmin=0.0, vmax=vmax, aspect="equal",
        )
        _style_heatmap_axis(ax1, "期望毁伤效能 V", show_y_axis=False)
        _add_percent_colorbar(figure, im1, ax1, "期望毁伤效能")

        # 标记 D 峰值和最佳瞄准点 (在两幅图上都标)
        for ax, extent in [(ax0, extent_d), (ax1, extent_v)]:
            # D 峰值: 红色 ×
            ax.plot(result.d_peak_x, result.d_peak_y, marker="x", ms=14,
                    mew=2.5, color="#DC2626", zorder=10)
            # 最佳瞄准点: 金色 ★
            ax.plot(result.best_x, result.best_y, marker="*", ms=16,
                    mec="white", mew=1.2, mfc="#F59E0B", zorder=11)

        # 在右图上添加标注
        ax1.annotate(
            f"★ 最佳瞄准点\n({result.best_x:.1f}, {result.best_y:.1f}) m\n"
            f"Vmax={result.vmax:.4f}",
            xy=(result.best_x, result.best_y), xytext=(12, 12),
            textcoords="offset points", fontsize=8, color="#F59E0B",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#F59E0B", alpha=0.9),
        )
        ax1.annotate(
            f"× D 峰值\n({result.d_peak_x:.1f}, {result.d_peak_y:.1f}) m",
            xy=(result.d_peak_x, result.d_peak_y), xytext=(-12, -25),
            textcoords="offset points", fontsize=8, color="#DC2626",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#DC2626", alpha=0.9),
        )

        return figure

    def _update_aim_summary(self, result: AimOptimizationResult) -> None:
        """在瞄准优化标签页底部显示结果摘要。"""
        frame = self.tab_frames.get("aim")
        if frame is None:
            return

        # 查找或创建摘要条
        summary_frame = getattr(self, "_aim_summary_frame", None)
        if summary_frame is not None:
            summary_frame.destroy()

        summary_frame = tk.Frame(frame, bg=CONFIG.ui_panel_bg, relief="flat",
                                 highlightbackground=CONFIG.ui_border,
                                 highlightthickness=1)
        summary_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 2))
        self._aim_summary_frame = summary_frame

        items = [
            ("最佳瞄准点", f"({result.best_x:.1f}, {result.best_y:.1f}) m"),
            ("Vmax", f"{result.vmax:.4f}"),
            ("相对直瞄增益", f"+{result.gain_relative:.2%}" if result.gain_relative >= 0
                            else f"{result.gain_relative:.2%}"),
            ("位移", f"{result.shift_distance:.1f} m"),
        ]
        for i, (label, value) in enumerate(items):
            cell = tk.Frame(summary_frame, bg=CONFIG.ui_panel_bg)
            cell.grid(row=0, column=i, sticky="ew", padx=8, pady=6)
            summary_frame.columnconfigure(i, weight=1)
            tk.Label(cell, text=label, bg=CONFIG.ui_panel_bg, fg=CONFIG.ui_muted,
                    font=("Microsoft YaHei", 9)).pack()
            tk.Label(cell, text=value, bg=CONFIG.ui_panel_bg, fg=CONFIG.ui_text,
                    font=("Microsoft YaHei", 11, "bold")).pack(pady=(2, 0))

    def _handle_error(self, title: str, exc: Exception) -> None:
        self._set_status(f"{title}: {exc}", kind="error")
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        messagebox.showerror(title, f"{exc}\n\n{detail}")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    app = DamagePredictionGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
