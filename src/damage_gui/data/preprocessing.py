"""场预处理：双边滤波降噪、坐标网格、ROI 掩膜与评估口径平滑。"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.ndimage import zoom

from damage_gui.config import Config, CONFIG


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


def coordinate_axes(
    shape: tuple[int, int],
    config: Config | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    config = config or CONFIG
    rows, cols = shape
    x_axis = np.linspace(config.coord_min, config.coord_max, cols, dtype=np.float32)
    y_axis = np.linspace(config.coord_min, config.coord_max, rows, dtype=np.float32)
    return x_axis, y_axis


def coordinate_grids(
    shape: tuple[int, int],
    config: Config | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    x_axis, y_axis = coordinate_axes(shape, config)
    return np.meshgrid(x_axis, y_axis)


def roi_mask_for_shape(
    shape: tuple[int, int],
    config: Config | None = None,
) -> np.ndarray:
    """返回有效建模区域 ROI 的布尔掩膜（ROI 外预测值恒为 0）。"""
    config = config or CONFIG
    if not config.use_roi:
        return np.ones(shape, dtype=bool)

    grid_x, grid_y = coordinate_grids(shape, config)
    return (
        (grid_x >= config.roi_x_min)
        & (grid_x <= config.roi_x_max)
        & (grid_y >= config.roi_y_min)
        & (grid_y <= config.roi_y_max)
    )


def roi_description(config: Config | None = None) -> str:
    config = config or CONFIG
    if not config.use_roi:
        return "全矩阵"
    return (
        f"x=[{config.roi_x_min:g}, {config.roi_x_max:g}], "
        f"y=[{config.roi_y_min:g}, {config.roi_y_max:g}]"
    )


def evaluation_fields(
    true_matrix: np.ndarray,
    pred_matrix: np.ndarray,
    config: Config | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """场级评估口径：真值与预测做同样的高斯低通（局部平均）后再逐点比较。

    降噪后的真值仍残留像素级蒙特卡洛噪声，直接逐点对比会把真值自身的
    噪声计入模型误差。展示用的热力图不经过此处理（保真）。
    Raw 口径指标（不平滑）同时保留在评估报告中。
    """
    config = config or CONFIG
    sigma = config.eval_smoothing_sigma
    if sigma <= 0:
        return true_matrix, pred_matrix
    return (
        gaussian_filter(true_matrix, sigma).astype(np.float32),
        gaussian_filter(pred_matrix, sigma).astype(np.float32),
    )
