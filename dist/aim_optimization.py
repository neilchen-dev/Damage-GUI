"""aim_optimization.py — 瞄准优化通用算法模块 (TASK 001-004)

从 aim_point_test.py (TASK 001/002) 中抽取的经过验证的通用数学函数。
不依赖 matplotlib，可被验证脚本、实验脚本和 GUI 共同调用。

=== 冻结假设 (TASK 004) ===
A1: D(x,y) 位于目标法平面
A2: CEP / REP / DEP 直接用于建立目标法平面上的散布概率模型
A3: x/y 两方向独立，rho = 0
A4: 最优瞄准点 = argmax(D*G)
A5: 边界外区域不额外建模
assumption_mode = "normal_plane_direct"

=== 术语约定 ===
- V = R*(D*G) 称为"期望毁伤效能 / 瞄准点价值"
- G 是"由连续高斯概率密度在网格中心采样后归一化得到的离散近似概率质量"
  （cell_integrated 版本才是真正的网格积分概率）

=== 散布参数接口 (TASK 004-1) ===
上层参数: CEP (圆形) 或 REP/DEP (椭圆)
内部统一转成: sigma_x, sigma_y, rho=0
  - CEP 模式:  sigma_x = sigma_y = CEP / 1.1774
  - REP/DEP:   sigma_x = REP / 0.6745,  sigma_y = DEP / 0.6745
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import fftconvolve


# ===================== CEP / sigma 转换 =====================

def cep_to_sigma(cep: float) -> float:
    """CEP 转 sigma（圆概率误差转标准差）。

    物理意义：
        CEP = 1.1774 * sigma （当 sigma_x = sigma_y = sigma 时）
        因此 sigma = CEP / 1.1774

    参数:
        cep: 圆概率误差（米）

    返回:
        标准差 sigma（米）
    """
    if cep < 0:
        raise ValueError(f"CEP 必须非负，当前为 {cep}")
    return cep / 1.1774


def rep_dep_to_sigma(
    rep: float,
    dep: float,
) -> tuple[float, float]:
    """REP / DEP 转 sigma_x / sigma_y（椭圆散布）。

    物理意义：
        REP (Range Error Probable) 是 x 方向（射程方向）的一维概率误差，
        即 P(|X| <= REP) = 0.5。
        DEP (Deflection Error Probable) 是 y 方向（偏航方向）的一维概率误差。
        对于一维正态分布：P(|X| <= a) = 0.5 当 a = 0.6745 * sigma。
        因此：
            sigma_x = REP / 0.6745
            sigma_y = DEP / 0.6745

    当前假设 (A2): REP/DEP 已经在目标法平面内，无需地平面→法平面转换。
    当前假设 (A3): x/y 独立，rho = 0。

    参数:
        rep: 射程概率误差（米），对应 x 方向
        dep: 偏航概率误差（米），对应 y 方向

    返回:
        (sigma_x, sigma_y): 标准差（米）
    """
    if rep < 0:
        raise ValueError(f"REP 必须非负，当前为 {rep}")
    if dep < 0:
        raise ValueError(f"DEP 必须非负，当前为 {dep}")
    PROBABLE_ERROR_FACTOR = 0.6745
    sigma_x = rep / PROBABLE_ERROR_FACTOR
    sigma_y = dep / PROBABLE_ERROR_FACTOR
    return sigma_x, sigma_y


# ===================== 正态分布 CDF =====================

def normal_cdf(
    x: float,
    mu: float,
    sigma: float,
) -> float:
    """正态分布累积分布函数 Φ(x; μ, σ)。

    使用 math.erf 实现：
        Φ(x) = 0.5 * [1 + erf((x - μ) / (σ√2))]
    """
    s = max(sigma, 1e-300)
    return 0.5 * (1.0 + math.erf((x - mu) / (s * math.sqrt(2.0))))


# ===================== 高斯散布核 =====================

def gaussian_kernel_from_cep(
    cep: float,
    pixel_size_x: float,
    pixel_size_y: float,
    truncate: float = 4.0,
) -> np.ndarray:
    """从 CEP 生成归一化的二维圆形高斯散布核（sampled 方法）。

    G[i,j] 是由连续高斯概率密度在网格中心采样后归一化得到的
    离散近似概率质量，非严格的单网格积分概率。
    当 sigma 相对网格尺寸较大时近似很好；
    当 sigma 远小于像素尺寸时，应使用 cell_integrated 版本或 delta 极限。

    CEP=0 时显式返回 1×1 delta 核 [[1.0]]。

    参数:
        cep: 圆概率误差（米），cep=0 时返回 delta 核
        pixel_size_x, pixel_size_y: 像素尺寸（米/像素）
        truncate: 截断倍数（以 sigma 为单位）

    返回:
        归一化高斯核（float64，sum = 1）
    """
    sigma = cep_to_sigma(cep)
    return gaussian_sampled_probability_kernel(
        sigma, sigma, pixel_size_x, pixel_size_y, truncate
    )


def gaussian_sampled_probability_kernel(
    sigma_x: float,
    sigma_y: float,
    pixel_size_x: float,
    pixel_size_y: float,
    truncate: float = 4.0,
) -> np.ndarray:
    """Build a sampled, axis-aligned Gaussian kernel from plane sigmas.

    ``sigma_x`` acts along matrix columns (physical x), while ``sigma_y``
    acts along matrix rows (physical y).  This is the TASK 004A entry point
    for an elliptical dispersion already expressed in the DamageMatrix plane.
    """
    for name, value in (("sigma_x", sigma_x), ("sigma_y", sigma_y)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    for name, value in (("pixel_size_x", pixel_size_x), ("pixel_size_y", pixel_size_y)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive, got {value}")
    if not math.isfinite(truncate) or truncate <= 0:
        raise ValueError(f"truncate must be finite and positive, got {truncate}")
    if sigma_x == 0 and sigma_y == 0:
        return np.array([[1.0]], dtype=np.float64)

    half_x = max(1, int(math.ceil(truncate * sigma_x / pixel_size_x))) if sigma_x > 0 else 1
    half_y = max(1, int(math.ceil(truncate * sigma_y / pixel_size_y))) if sigma_y > 0 else 1
    x = np.arange(-half_x, half_x + 1, dtype=np.float64) * pixel_size_x
    y = np.arange(-half_y, half_y + 1, dtype=np.float64) * pixel_size_y
    wx = np.exp(-0.5 * (x / sigma_x) ** 2) if sigma_x > 0 else (x == 0).astype(float)
    wy = np.exp(-0.5 * (y / sigma_y) ** 2) if sigma_y > 0 else (y == 0).astype(float)
    kernel = np.outer(wy, wx)
    total = float(kernel.sum())
    if total < 1e-300:
        kernel = np.zeros_like(kernel)
        kernel[half_y, half_x] = 1.0
    else:
        kernel /= total
    return kernel


def gaussian_cell_probability_kernel(
    sigma_x: float,
    sigma_y: float,
    pixel_size_x: float,
    pixel_size_y: float,
    truncate: float = 4.0,
) -> np.ndarray:
    """生成网格积分概率核（cell_integrated 方法）。

    每个单元格的概率使用 CDF 差计算（真正的单网格积分概率）：
        P_x = Φ(x + Δx/2) - Φ(x - Δx/2)
        P_y = Φ(y + Δy/2) - Φ(y - Δy/2)
        P_ij = P_y_i * P_x_j  （二维独立）

    参数:
        sigma_x, sigma_y: 标准差（米）
        pixel_size_x, pixel_size_y: 像素尺寸（米/像素）
        truncate: 截断倍数

    返回:
        归一化网格积分概率核（float64，sum ≈ 1）
    """
    for name, value in (("sigma_x", sigma_x), ("sigma_y", sigma_y)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    for name, value in (("pixel_size_x", pixel_size_x), ("pixel_size_y", pixel_size_y)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive, got {value}")
    if not math.isfinite(truncate) or truncate <= 0:
        raise ValueError(f"truncate must be finite and positive, got {truncate}")
    if sigma_x == 0 and sigma_y == 0:
        return np.array([[1.0]], dtype=np.float64)

    sx = max(sigma_x, 1e-10)
    sy = max(sigma_y, 1e-10)

    half_x = max(1, int(math.ceil(truncate * sx / pixel_size_x)))
    half_y = max(1, int(math.ceil(truncate * sy / pixel_size_y)))

    x_centers = np.arange(-half_x, half_x + 1, dtype=np.float64) * pixel_size_x
    x_lower = x_centers - pixel_size_x / 2.0
    x_upper = x_centers + pixel_size_x / 2.0
    px_probs = np.array([
        normal_cdf(xu, 0.0, sx) - normal_cdf(xl, 0.0, sx)
        for xl, xu in zip(x_lower, x_upper)
    ])

    y_centers = np.arange(-half_y, half_y + 1, dtype=np.float64) * pixel_size_y
    y_lower = y_centers - pixel_size_y / 2.0
    y_upper = y_centers + pixel_size_y / 2.0
    py_probs = np.array([
        normal_cdf(yu, 0.0, sy) - normal_cdf(yl, 0.0, sy)
        for yl, yu in zip(y_lower, y_upper)
    ])

    kernel = np.outer(py_probs, px_probs)

    total = kernel.sum()
    if total < 1e-300:
        kernel = np.zeros_like(kernel)
        kernel[half_y, half_x] = 1.0
    else:
        kernel = kernel / total

    return kernel


# ===================== 价值场计算 =====================

def compute_aim_value_field(
    damage_matrix: np.ndarray,
    cep: float,
    coord_min: float,
    coord_max: float,
    reliability: float = 1.0,
    kernel_method: str = "cell_integrated",
) -> tuple[np.ndarray, np.ndarray]:
    """计算瞄准点价值场 V = R * fftconvolve(D, G, mode="same")。

    物理意义：
        V[row, col] 表示当瞄准点放在像素 (row, col) 对应的物理坐标时的
        期望毁伤效能。

    坐标约定（与主干 coordinate_axes 一致）：
        x = coord_min + col * px （列）
        y = coord_min + row * py （行）

    参数:
        damage_matrix: 毁伤矩阵 D[i,j]
        cep: 圆概率误差（米），cep=0 时退化为 V=R*D
        coord_min, coord_max: 坐标范围（米）
        reliability: 弹药可靠度 R ∈ (0, 1]
        kernel_method: "cell_integrated"（默认，推荐）或 "sampled"

    返回:
        (value_field, kernel)
    """
    if not (0.0 < reliability <= 1.0):
        raise ValueError(f"可靠度 R 必须在 (0, 1] 范围内，当前为 {reliability}")
    if cep < 0:
        raise ValueError(f"CEP 必须非负，当前为 {cep}")

    sigma = cep_to_sigma(cep)
    return compute_aim_value_field_from_sigmas(
        damage_matrix, sigma, sigma, coord_min, coord_max,
        reliability=reliability, kernel_method=kernel_method,
    )


def compute_aim_value_field_from_sigmas(
    damage_matrix: np.ndarray,
    sigma_x: float,
    sigma_y: float,
    coord_min: float,
    coord_max: float,
    reliability: float = 1.0,
    kernel_method: str = "cell_integrated",
) -> tuple[np.ndarray, np.ndarray]:
    """Compute ``V = R * (D * G)`` for plane-aligned elliptical dispersion.

    The function intentionally accepts sigmas already expressed in the same
    normal plane and units as ``damage_matrix``.  Ground-to-normal-plane
    conversion, REP/DEP axis assignment, impact angle and correlation remain
    outside this function until their physical definitions are confirmed.
    """
    if not (0.0 < reliability <= 1.0):
        raise ValueError(f"reliability must be in (0, 1], got {reliability}")
    for name, value in (("sigma_x", sigma_x), ("sigma_y", sigma_y)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    if kernel_method not in {"cell_integrated", "sampled"}:
        raise ValueError(
            f"kernel_method must be 'cell_integrated' or 'sampled', got {kernel_method!r}"
        )
    matrix = np.asarray(damage_matrix)
    if matrix.ndim != 2:
        raise ValueError(f"damage_matrix must be 2-D, got shape {matrix.shape}")
    rows, cols = matrix.shape
    if rows < 2 or cols < 2 or not math.isfinite(coord_min) or not math.isfinite(coord_max) or coord_max <= coord_min:
        raise ValueError("damage_matrix must be at least 2x2 and coord_max must exceed coord_min")
    px = (coord_max - coord_min) / (cols - 1)
    py = (coord_max - coord_min) / (rows - 1)
    if kernel_method == "cell_integrated":
        kernel = gaussian_cell_probability_kernel(sigma_x, sigma_y, px, py)
    else:
        kernel = gaussian_sampled_probability_kernel(sigma_x, sigma_y, px, py)
    value_field = reliability * fftconvolve(matrix.astype(np.float64), kernel, mode="same")
    return np.maximum(value_field, 0.0), kernel


# ===================== 最佳瞄准点 =====================

def find_best_aim_point(
    value_field: np.ndarray,
) -> tuple[int, int, float]:
    """找到价值场中的最佳瞄准点（argmax）。

    返回:
        (best_row, best_col, p_max)
    """
    flat_idx = int(np.argmax(value_field))
    best_row, best_col = divmod(flat_idx, value_field.shape[1])
    p_max = float(value_field[best_row, best_col])
    return int(best_row), int(best_col), p_max


# ===================== 坐标转换 =====================

def index_to_xy(
    row: int,
    col: int,
    shape: tuple[int, int],
    coord_min: float,
    coord_max: float,
) -> tuple[float, float]:
    """像素索引转物理坐标。

    x = coord_min + col * px（列），y = coord_min + row * py（行）
    """
    rows, cols = shape
    px = (coord_max - coord_min) / max(cols - 1, 1)
    py = (coord_max - coord_min) / max(rows - 1, 1)
    x = coord_min + col * px
    y = coord_min + row * py
    return x, y


def xy_to_index(
    x: float,
    y: float,
    shape: tuple[int, int],
    coord_min: float,
    coord_max: float,
) -> tuple[int, int]:
    """物理坐标转像素索引（最近网格点）。"""
    rows, cols = shape
    px = (coord_max - coord_min) / max(cols - 1, 1)
    py = (coord_max - coord_min) / max(rows - 1, 1)
    col = int(round((x - coord_min) / px))
    row = int(round((y - coord_min) / py))
    col = max(0, min(cols - 1, col))
    row = max(0, min(rows - 1, row))
    return row, col


def value_at_physical_aim(
    value_field: np.ndarray,
    aim_x: float,
    aim_y: float,
    coord_min: float,
    coord_max: float,
) -> float:
    """从价值场中提取指定物理坐标处的值（最近网格点采样）。

    注意：离散最近点采样，存在 ≤ 0.5 像素的量化误差。
    """
    row, col = xy_to_index(aim_x, aim_y, value_field.shape, coord_min, coord_max)
    return float(value_field[row, col])


# ===================== 教材矩形目标解析公式 =====================

def rectangular_hit_probability_analytic(
    aim_x: float,
    aim_y: float,
    half_length_x: float,
    half_width_y: float,
    sigma_x: float,
    sigma_y: float,
) -> float:
    """矩形目标命中概率解析解（教材式 P_H = P_{H/x} * P_{H/y}）。

    矩形目标以原点为中心。
    """
    px = normal_cdf(half_length_x, aim_x, sigma_x) - normal_cdf(-half_length_x, aim_x, sigma_x)
    py = normal_cdf(half_width_y, aim_y, sigma_y) - normal_cdf(-half_width_y, aim_y, sigma_y)
    return px * py


def build_rectangular_binary_target(
    coord_min: float,
    coord_max: float,
    pixel_size: float,
    length_x: float,
    width_y: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """构造 0/1 矩形目标毁伤矩阵。矩形内部 D=1，外部 D=0。"""
    n = int(round((coord_max - coord_min) / pixel_size)) + 1
    x_axis = np.linspace(coord_min, coord_max, n)
    y_axis = np.linspace(coord_min, coord_max, n)
    X, Y = np.meshgrid(x_axis, y_axis)
    D = np.zeros((n, n), dtype=np.float64)
    D[(np.abs(X) <= length_x / 2.0) & (np.abs(Y) <= width_y / 2.0)] = 1.0
    return D, x_axis, y_axis


# ===================== 统一 facade (TASK 005) =====================

@dataclass
class AimOptimizationResult:
    """瞄准优化统一结果结构。"""
    value_field: np.ndarray
    kernel: np.ndarray

    spread_mode: str
    sigma_x: float
    sigma_y: float
    reliability: float

    d_peak_x: float
    d_peak_y: float
    d_peak_value: float

    best_row: int
    best_col: int
    best_x: float
    best_y: float
    vmax: float

    v_at_d_peak: float
    shift_distance: float
    gain_absolute: float
    gain_relative: float


def optimize_aim(
    damage_matrix: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    *,
    spread_mode: str = "CEP",
    cep: float | None = None,
    rep: float | None = None,
    dep: float | None = None,
    reliability: float = 1.0,
    kernel_method: str = "cell_integrated",
) -> AimOptimizationResult:
    """GUI 统一瞄准优化接口。

    参数:
        damage_matrix: 毁伤矩阵 D（来自 RBF 预测）
        x_axis, y_axis: 物理坐标轴（来自 coordinate_axes）
        spread_mode: "CEP" 或 "REP_DEP"
        cep: CEP 值（CEP 模式时必填）
        rep, dep: REP/DEP 值（REP_DEP 模式时必填）
        reliability: 可靠度 R（默认 1.0）
        kernel_method: "cell_integrated" 或 "sampled"

    返回:
        AimOptimizationResult
    """
    rows, cols = damage_matrix.shape
    coord_min = float(min(x_axis[0], y_axis[0]))
    coord_max = float(max(x_axis[-1], y_axis[-1]))

    # 散布参数转换
    if spread_mode == "CEP":
        if cep is None:
            raise ValueError("CEP 模式需要 cep 参数")
        sigma = cep_to_sigma(cep)
        sigma_x, sigma_y = sigma, sigma
    elif spread_mode == "REP_DEP":
        if rep is None or dep is None:
            raise ValueError("REP_DEP 模式需要 rep 和 dep 参数")
        sigma_x, sigma_y = rep_dep_to_sigma(rep, dep)
    else:
        raise ValueError(f"未知 spread_mode: {spread_mode}")

    # 计算价值场
    if spread_mode == "CEP":
        cep_val = cep if cep is not None else 0.0
        value_field, kernel = compute_aim_value_field(
            damage_matrix, cep_val, coord_min, coord_max,
            reliability, kernel_method,
        )
    else:
        value_field, kernel = compute_aim_value_field_from_sigmas(
            damage_matrix, sigma_x, sigma_y, coord_min, coord_max,
            reliability, kernel_method,
        )

    # D 峰值
    d_peak_flat = int(np.argmax(damage_matrix))
    d_peak_r, d_peak_c = divmod(d_peak_flat, cols)
    px = (coord_max - coord_min) / max(cols - 1, 1)
    py = (coord_max - coord_min) / max(rows - 1, 1)
    d_peak_x = float(coord_min + d_peak_c * px)
    d_peak_y = float(coord_min + d_peak_r * py)
    d_peak_value = float(damage_matrix[d_peak_r, d_peak_c])

    # 最佳瞄准点
    best_row, best_col, vmax = find_best_aim_point(value_field)
    best_x = float(coord_min + best_col * px)
    best_y = float(coord_min + best_row * py)

    # V@D_peak
    v_at_d_peak = value_at_physical_aim(value_field, d_peak_x, d_peak_y, coord_min, coord_max)

    # 增益
    shift = math.hypot(best_x - d_peak_x, best_y - d_peak_y)
    gain_abs = vmax - v_at_d_peak
    gain_rel = gain_abs / v_at_d_peak if v_at_d_peak > 1e-12 else 0.0

    return AimOptimizationResult(
        value_field=value_field,
        kernel=kernel,
        spread_mode=spread_mode,
        sigma_x=sigma_x,
        sigma_y=sigma_y,
        reliability=reliability,
        d_peak_x=d_peak_x,
        d_peak_y=d_peak_y,
        d_peak_value=d_peak_value,
        best_row=best_row,
        best_col=best_col,
        best_x=best_x,
        best_y=best_y,
        vmax=vmax,
        v_at_d_peak=v_at_d_peak,
        shift_distance=shift,
        gain_absolute=gain_abs,
        gain_relative=gain_rel,
    )
