"""aim_optimization.py — 瞄准优化通用算法模块 (TASK 001-004)

从 aim_point_test.py (TASK 001/002) 中抽取的经过验证的通用数学函数。
不依赖 matplotlib，可被验证脚本、实验脚本和 GUI 共同调用。

=== 冻结假设 (TASK 004) ===
A1: D(x,y) 位于目标法平面
A2: CEP / REP / DEP 直接用于建立目标法平面上的散布概率模型
A3: x/y 两方向独立，rho = 0（默认）；rho != 0 时启用相关散布椭圆扩展
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


# ===================== 相关散布 (rho != 0) 与旋转椭圆 =====================

def rotation_to_covariance(
    sigma_u: float,
    sigma_v: float,
    theta: float,
) -> tuple[float, float, float]:
    """旋转散布椭圆的协方差参数化。

    物理意义：
        主轴标准差 sigma_u 沿与 x 轴夹角 theta 的方向，次轴 sigma_v 与之垂直。
        将协方差矩阵 Σ = R(θ) diag(σu², σv²) R(θ)ᵀ 展开得到平面 (x, y) 坐标下的
        (σx, σy, ρ)：
            σx² = σu²cos²θ + σv²sin²θ
            σy² = σu²sin²θ + σv²cos²θ
            cov = (σu² − σv²) sinθcosθ，ρ = cov / (σxσy)

    参数:
        sigma_u, sigma_v: 椭圆主/次轴标准差（米），需非负
        theta: 主轴相对 x 轴的旋转角（弧度）

    返回:
        (sigma_x, sigma_y, rho)，rho 裁剪到 (−1, 1) 开区间内避免奇异
    """
    for name, value in (("sigma_u", sigma_u), ("sigma_v", sigma_v)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    if not math.isfinite(theta):
        raise ValueError(f"theta must be finite, got {theta}")

    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    sigma_x_sq = sigma_u**2 * cos_t**2 + sigma_v**2 * sin_t**2
    sigma_y_sq = sigma_u**2 * sin_t**2 + sigma_v**2 * cos_t**2
    cov = (sigma_u**2 - sigma_v**2) * sin_t * cos_t

    sigma_x = math.sqrt(sigma_x_sq)
    sigma_y = math.sqrt(sigma_y_sq)
    axis_tolerance = max(sigma_u, sigma_v, 1.0) * 1e-12
    if sigma_x <= axis_tolerance:
        sigma_x = 0.0
    if sigma_y <= axis_tolerance:
        sigma_y = 0.0
    denom = sigma_x * sigma_y
    if denom <= 0.0:
        # 协方差恰好与坐标轴对齐且单轴退化时，相关系数无定义但协方差为 0；
        # 必须保留另一条非零轴，不能把整条线散布误降为 delta 核。
        return sigma_x, sigma_y, 0.0
    rho = cov / denom
    rho = max(-1.0 + 1e-9, min(1.0 - 1e-9, rho))
    return sigma_x, sigma_y, rho


def correlated_gaussian_kernel(
    sigma_x: float,
    sigma_y: float,
    rho: float,
    pixel_size_x: float,
    pixel_size_y: float,
    truncate: float = 4.0,
) -> np.ndarray:
    """ρ ≠ 0 的二维相关高斯散布核（cell 中心采样后归一化）。

    密度函数：
        f(x, y) ∝ exp( −1/(2(1−ρ²)) · [ (x/σx)² − 2ρxy/(σxσy) + (y/σy)² ] )

    截断条件为广义马氏距离 d² = Mahalanobis² <= truncate²。
    与轴对齐 sampled 版本相同，概率质量由中心采样归一化近似；
    σ 远大于像素尺寸时近似良好（与 cell_integrated 的差异 O((pixel/σ)²)）。
    ρ=0 时与 gaussian_sampled_probability_kernel 的差异仅来自截断窗口
    形状（本函数为椭圆马氏截断，sampled 为方形窗口），量级
    O(e^{−truncate²/2})，可忽略。
    """
    for name, value in (("sigma_x", sigma_x), ("sigma_y", sigma_y)):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative, got {value}")
    if not math.isfinite(rho) or abs(rho) >= 1.0:
        raise ValueError(f"rho must be a finite correlation in (-1, 1), got {rho}")
    for name, value in (("pixel_size_x", pixel_size_x), ("pixel_size_y", pixel_size_y)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive, got {value}")
    if not math.isfinite(truncate) or truncate <= 0:
        raise ValueError(f"truncate must be finite and positive, got {truncate}")
    if sigma_x == 0.0 and sigma_y == 0.0:
        return np.array([[1.0]], dtype=np.float64)

    sx = max(sigma_x, 1e-10)
    sy = max(sigma_y, 1e-10)
    one_minus_rho_sq = max(1.0 - rho * rho, 1e-12)

    half_x = max(1, int(math.ceil(truncate * max(sx, sy) / pixel_size_x)))
    half_y = max(1, int(math.ceil(truncate * max(sx, sy) / pixel_size_y)))
    x = np.arange(-half_x, half_x + 1, dtype=np.float64) * pixel_size_x
    y = np.arange(-half_y, half_y + 1, dtype=np.float64) * pixel_size_y
    grid_x, grid_y = np.meshgrid(x, y)

    zx = grid_x / sx
    zy = grid_y / sy
    mahalanobis_sq = (zx * zx - 2.0 * rho * zx * zy + zy * zy) / one_minus_rho_sq
    kernel = np.where(mahalanobis_sq <= truncate**2, np.exp(-0.5 * mahalanobis_sq), 0.0)

    total = float(kernel.sum())
    if total < 1e-300:
        kernel = np.zeros_like(kernel)
        kernel[half_y, half_x] = 1.0
    else:
        kernel /= total
    return kernel


# ===================== Monte Carlo 独立验证 =====================

@dataclass
class MonteCarloResult:
    """Monte Carlo 期望毁伤效能估计（用于独立验证解析卷积价值场）。"""

    mean: float
    std_error: float
    n_samples: int

    @property
    def ci_half_width_95(self) -> float:
        """95% 置信区间半宽 ≈ 1.96 · 标准误。"""
        return 1.96 * self.std_error


def monte_carlo_expected_damage(
    damage_matrix: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    aim_x: float,
    aim_y: float,
    sigma_x: float,
    sigma_y: float,
    rho: float = 0.0,
    n_samples: int = 20000,
    reliability: float = 1.0,
    random_state: int = 0,
) -> MonteCarloResult:
    """Monte Carlo 估计瞄准点期望毁伤效能（对解析卷积的独立验证）。

    从二维正态 N((aim_x, aim_y), Σ)（Σ 含相关系数 ρ）采样 n 个落点，
    落点处毁伤值用双线性插值读取（网格外为 0），平均后乘以可靠度 R。
    与解析价值场 V(aim) = R·(D∗G)(aim) 走完全不同的数学路径，
    二者一致即可相互验证实现正确性。

    返回:
        MonteCarloResult(mean, std_error, n_samples)
    """
    from scipy.ndimage import map_coordinates

    if n_samples < 1:
        raise ValueError(f"n_samples must be positive, got {n_samples}")
    if not (0.0 < reliability <= 1.0):
        raise ValueError(f"reliability must be in (0, 1], got {reliability}")
    if not math.isfinite(rho) or abs(rho) >= 1.0:
        raise ValueError(f"rho must be a finite correlation in (-1, 1), got {rho}")
    for name, value in (
        ("aim_x", aim_x),
        ("aim_y", aim_y),
        ("sigma_x", sigma_x),
        ("sigma_y", sigma_y),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value}")
    if sigma_x < 0 or sigma_y < 0:
        raise ValueError(
            f"sigma_x and sigma_y must be non-negative, got {sigma_x}, {sigma_y}"
        )

    matrix = np.asarray(damage_matrix, dtype=np.float64)
    x_axis = np.asarray(x_axis, dtype=np.float64)
    y_axis = np.asarray(y_axis, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError(f"damage_matrix must be 2-D, got shape {matrix.shape}")
    if x_axis.ndim != 1 or y_axis.ndim != 1:
        raise ValueError("x_axis and y_axis must be one-dimensional")
    if len(x_axis) != matrix.shape[1] or len(y_axis) != matrix.shape[0]:
        raise ValueError(
            "axis lengths must match damage_matrix shape: "
            f"matrix={matrix.shape}, x={len(x_axis)}, y={len(y_axis)}"
        )
    if len(x_axis) < 2 or len(y_axis) < 2:
        raise ValueError("x_axis and y_axis must each contain at least two points")
    dx = np.diff(x_axis)
    dy = np.diff(y_axis)
    if np.any(dx <= 0) or np.any(dy <= 0):
        raise ValueError("x_axis and y_axis must be strictly increasing")
    if not np.allclose(dx, dx[0]) or not np.allclose(dy, dy[0]):
        raise ValueError("x_axis and y_axis must be uniformly spaced")
    cov = (
        np.array(
            [
                [sigma_x**2, rho * sigma_x * sigma_y],
                [rho * sigma_x * sigma_y, sigma_y**2],
            ],
            dtype=np.float64,
        )
        if (sigma_x > 0 or sigma_y > 0)
        else np.zeros((2, 2))
    )

    rng = np.random.default_rng(random_state)
    if np.allclose(cov, 0.0):
        offsets = np.zeros((n_samples, 2))
    else:
        offsets = rng.multivariate_normal(np.zeros(2), cov, size=n_samples)

    sample_x = aim_x + offsets[:, 0]
    sample_y = aim_y + offsets[:, 1]

    px = float(dx[0])
    py = float(dy[0])
    cols = (sample_x - float(x_axis[0])) / px
    rows = (sample_y - float(y_axis[0])) / py

    values = map_coordinates(matrix, [rows, cols], order=1, mode="constant", cval=0.0)
    scaled = reliability * values
    mean = float(scaled.mean())
    std_error = float(scaled.std(ddof=1) / math.sqrt(n_samples)) if n_samples > 1 else 0.0
    return MonteCarloResult(mean=mean, std_error=std_error, n_samples=int(n_samples))


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
    rho: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute ``V = R * (D * G)`` for plane-aligned elliptical dispersion.

    The function intentionally accepts sigmas already expressed in the same
    normal plane and units as ``damage_matrix``.  Ground-to-normal-plane
    conversion, REP/DEP axis assignment, impact angle and correlation remain
    outside this function until their physical definitions are confirmed.

    ``rho != 0`` selects the correlated (rotated-ellipse) Gaussian kernel
    built by :func:`correlated_gaussian_kernel`; in that case
    ``kernel_method`` is ignored (only the sampled approximation is
    available for correlated kernels).
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
    if not math.isfinite(rho) or abs(rho) >= 1.0:
        raise ValueError(f"rho must be a finite correlation in (-1, 1), got {rho}")
    matrix = np.asarray(damage_matrix)
    if matrix.ndim != 2:
        raise ValueError(f"damage_matrix must be 2-D, got shape {matrix.shape}")
    rows, cols = matrix.shape
    if rows < 2 or cols < 2 or not math.isfinite(coord_min) or not math.isfinite(coord_max) or coord_max <= coord_min:
        raise ValueError("damage_matrix must be at least 2x2 and coord_max must exceed coord_min")
    px = (coord_max - coord_min) / (cols - 1)
    py = (coord_max - coord_min) / (rows - 1)
    if rho != 0.0:
        kernel = correlated_gaussian_kernel(sigma_x, sigma_y, rho, px, py)
    elif kernel_method == "cell_integrated":
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
    rho: float = 0.0


def optimize_aim(
    damage_matrix: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    *,
    spread_mode: str = "CEP",
    cep: float | None = None,
    rep: float | None = None,
    dep: float | None = None,
    rho: float = 0.0,
    theta_deg: float | None = None,
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
        rho: x/y 方向相关系数 ∈ (−1, 1)，默认 0（独立）。仅 REP_DEP 模式生效
        theta_deg: REP_DEP 模式下散布椭圆主轴（REP 方向）相对 x 轴的旋转角
            （度）。给定后由 (σu, σv, θ) 旋转出平面协方差 (σx, σy, ρ)，
            此时 rho 参数被忽略
        reliability: 可靠度 R（默认 1.0）
        kernel_method: "cell_integrated" 或 "sampled"（rho != 0 时自动使用
            相关核的采样近似，该参数被忽略）

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
        if theta_deg is not None:
            raise ValueError("theta_deg 仅在 REP_DEP 模式下有意义")
        if rho != 0.0:
            # CEP 是圆形散布（各向同性），相关系数无定义；旋转椭圆请用 REP_DEP
            raise ValueError("rho != 0 时请使用 REP_DEP 模式（CEP 为圆形散布）")
        sigma = cep_to_sigma(cep)
        sigma_x, sigma_y = sigma, sigma
    elif spread_mode == "REP_DEP":
        if rep is None or dep is None:
            raise ValueError("REP_DEP 模式需要 rep 和 dep 参数")
        sigma_u, sigma_v = rep_dep_to_sigma(rep, dep)
        if theta_deg is not None:
            sigma_x, sigma_y, rho = rotation_to_covariance(
                sigma_u, sigma_v, math.radians(theta_deg)
            )
        else:
            sigma_x, sigma_y = sigma_u, sigma_v
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
            reliability, kernel_method, rho=rho,
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
        rho=rho,
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
