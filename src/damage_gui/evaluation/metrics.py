"""评价指标：数值强度指标、混合误差与二维空间场专用指标。

数值指标（RMSE / MAE / R² / 相对误差 / P95 混合误差）衡量像素级强度一致性；
空间指标（质心误差 / 峰值位置与强度误差 / IoU / Dice）衡量毁伤区域的
空间位置与形状重合程度——这是二维场预测问题不可缺失的评价维度。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.ndimage import center_of_mass as ndi_center_of_mass
from sklearn.metrics import (
    max_error,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from damage_gui.config import Config, CONFIG

# 空间场指标列名（统一出现在指标报告中，非空间行置 NaN）
SPATIAL_KEYS = (
    "CentroidError",
    "PeakIntensityError",
    "PeakPositionError",
    "IoU",
    "Dice",
)

_METRIC_KEYS = (
    "scope",
    "points",
    "MSE",
    "RMSE",
    "MAE",
    "R2",
    "MaxError",
    "TrueDamageAreaRatio",
    "PredDamageAreaRatio",
    "AreaRatioGap",
    "MeanRelativeError",
    "P90RelativeError",
    "MaxRelativeError",
    "P95HybridError",
    "MaxHybridError",
    "HybridAccuracyInTarget",
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
    config: Config | None = None,
) -> dict[str, float | str]:
    """计算误差指标。

    相对误差只在主要毁伤区域 damage > config.relative_error_threshold 内统计，
    避免真实值接近 0 时相对误差被异常放大。
    核心指标为平均相对误差与 P95 混合误差（混合误差见 Config.hybrid_error_floor 注释），
    最大相对误差作为参考项保留。
    对 overall / roi_overall 等非主要毁伤区域统计，相对误差字段置为 NaN。
    """
    config = config or CONFIG
    y_true = np.asarray(y_true, dtype=np.float32)
    y_pred = np.asarray(y_pred, dtype=np.float32)
    if y_true.size == 0:
        row = {key: np.nan for key in _METRIC_KEYS}
        row["scope"] = scope
        row["points"] = 0
        row.update({key: np.nan for key in SPATIAL_KEYS})
        return row

    mse_value = float(mean_squared_error(y_true, y_pred))
    rmse_value = float(math.sqrt(mse_value))
    mae_value = float(mean_absolute_error(y_true, y_pred))
    true_ratio = float(np.mean(y_true > area_threshold))
    pred_ratio = float(np.mean(y_pred > area_threshold))

    if (
        area_threshold >= config.relative_error_threshold
        and np.all(y_true > area_threshold)
    ):
        abs_error = np.abs(y_pred - y_true)
        relative_error = abs_error / y_true
        hybrid_error = abs_error / np.maximum(y_true, config.hybrid_error_floor)
        mean_relative_error = float(np.mean(relative_error))
        p90_relative_error = float(np.quantile(relative_error, 0.90))
        max_relative_error = float(np.max(relative_error))
        p95_hybrid_error = float(np.quantile(hybrid_error, 0.95))
        max_hybrid_error = float(np.max(hybrid_error))
        hybrid_accuracy = float(np.mean(hybrid_error < config.relative_error_target))
    else:
        mean_relative_error = np.nan
        p90_relative_error = np.nan
        max_relative_error = np.nan
        p95_hybrid_error = np.nan
        max_hybrid_error = np.nan
        hybrid_accuracy = np.nan

    row: dict[str, float | str] = {
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
    row.update({key: np.nan for key in SPATIAL_KEYS})
    return row


# ===================== 二维空间场专用指标 =====================

def field_centroid(matrix: np.ndarray) -> tuple[float, float] | None:
    """强度加权质心（像素坐标）。近零场返回 None。"""
    matrix = np.asarray(matrix, dtype=np.float64)
    if float(matrix.sum()) <= 1e-6:
        return None
    cy, cx = ndi_center_of_mass(matrix)
    return float(cy), float(cx)


def peak_position(matrix: np.ndarray) -> tuple[int, int]:
    """峰值位置（行, 列）。"""
    matrix = np.asarray(matrix)
    flat = int(np.argmax(matrix))
    row, col = divmod(flat, matrix.shape[1])
    return row, col


def spatial_metrics(
    true_matrix: np.ndarray,
    pred_matrix: np.ndarray,
    damage_threshold: float,
    pixel_size_x: float,
    pixel_size_y: float | None = None,
) -> dict[str, float]:
    """二维场空间结构指标（在 Raw 场上计算，不做平滑）。

    - CentroidError: 强度加权质心欧氏距离（米）——毁伤区域位置是否正确
    - PeakIntensityError: 峰值强度之差的绝对值
    - PeakPositionError: 峰值位置欧氏距离（米）
    - IoU / Dice: damage > threshold 二值化后的区域重合度；
      双方均无毁伤区时定义为 1（完全一致）
    """
    if pixel_size_y is None:
        pixel_size_y = pixel_size_x
    true_matrix = np.asarray(true_matrix, dtype=np.float64)
    pred_matrix = np.asarray(pred_matrix, dtype=np.float64)

    centroid_true = field_centroid(true_matrix)
    centroid_pred = field_centroid(pred_matrix)
    if centroid_true is not None and centroid_pred is not None:
        dy = (centroid_pred[0] - centroid_true[0]) * pixel_size_y
        dx = (centroid_pred[1] - centroid_true[1]) * pixel_size_x
        centroid_error = float(math.hypot(dx, dy))
    else:
        centroid_error = float("nan")

    peak_intensity_error = float(abs(true_matrix.max() - pred_matrix.max()))
    pt = peak_position(true_matrix)
    pp = peak_position(pred_matrix)
    peak_position_error = float(
        math.hypot(
            (pp[1] - pt[1]) * pixel_size_x,
            (pp[0] - pt[0]) * pixel_size_y,
        )
    )

    true_mask = true_matrix > damage_threshold
    pred_mask = pred_matrix > damage_threshold
    intersection = int(np.logical_and(true_mask, pred_mask).sum())
    union = int(np.logical_or(true_mask, pred_mask).sum())
    total_area = int(true_mask.sum()) + int(pred_mask.sum())
    iou = intersection / union if union > 0 else 1.0
    dice = 2.0 * intersection / total_area if total_area > 0 else 1.0

    return {
        "CentroidError": centroid_error,
        "PeakIntensityError": peak_intensity_error,
        "PeakPositionError": peak_position_error,
        "IoU": float(iou),
        "Dice": float(dice),
    }


# ===================== 摘要格式化 =====================

def extract_core_metrics(
    accuracy_report: pd.DataFrame,
    config: Config | None = None,
) -> tuple[float | None, float | None]:
    """提取 Smoothed 主要毁伤区的 Mean RE 与 P95 Hybrid。"""
    if accuracy_report.empty:
        return None, None
    config = config or CONFIG
    focus_scope = f"damage_gt_{config.relative_error_threshold:.2f}"
    focus = accuracy_report[accuracy_report["scope"] == focus_scope]
    if "field" in accuracy_report.columns:
        focus = focus[focus["field"] == "smoothed"]
    if focus.empty or pd.isna(focus.iloc[0].get("MeanRelativeError", np.nan)):
        return None, None
    return (
        float(focus.iloc[0]["MeanRelativeError"]),
        float(focus.iloc[0]["P95HybridError"]),
    )


def format_core_metrics(
    accuracy_report: pd.DataFrame,
    config: Config | None = None,
) -> str:
    """格式化评估摘要：核心指标为平均相对误差与 P95 混合误差。

    同时输出 Raw / Smoothed 双口径与空间指标摘要，说明两种口径的
    统计含义，避免"通过平滑刷指标"的质疑。
    """
    if accuracy_report.empty:
        return ""

    config = config or CONFIG
    lines: list[str] = []
    target = config.relative_error_target
    focus_scope = f"damage_gt_{config.relative_error_threshold:.2f}"

    for field, note in (
        ("smoothed", "局部平均场口径"),
        ("raw", "Raw 逐像素口径"),
    ):
        if "field" in accuracy_report.columns:
            focus = accuracy_report[
                (accuracy_report["scope"] == focus_scope)
                & (accuracy_report["field"] == field)
            ]
        else:
            if field != "smoothed":
                continue
            focus = accuracy_report[accuracy_report["scope"] == focus_scope]
        if focus.empty:
            continue
        row = focus.iloc[0]
        mean_re = row.get("MeanRelativeError", np.nan)
        p95_hybrid = row.get("P95HybridError", np.nan)
        if pd.isna(mean_re):
            continue
        prefix = "" if field == "smoothed" else "Raw "
        mean_flag = "✔达标" if mean_re < target else "✘未达标"
        hybrid_flag = "✔达标" if p95_hybrid < target else "✘未达标"
        lines.append(
            f"核心指标 ({prefix}毁伤区 damage>"
            f"{config.relative_error_threshold:g}, {note}, 目标<{target:.0%})"
        )
        lines.append(f"{prefix}平均相对误差 = {mean_re:.2%}  {mean_flag}")
        lines.append(f"{prefix}P95混合误差 = {p95_hybrid:.2%}  {hybrid_flag}")
        lines.append(
            f"{prefix}点达标率(混合<{target:.0%}) = {row['HybridAccuracyInTarget']:.2%}"
        )
        lines.append("")

    if "field" in accuracy_report.columns:
        spatial = accuracy_report[accuracy_report["scope"] == "spatial"]
        if not spatial.empty and not pd.isna(spatial.iloc[0].get("IoU", np.nan)):
            row = spatial.iloc[0]
            lines.append(
                "空间指标 (Raw 场): "
                f"质心误差={row['CentroidError']:.2f} m, "
                f"峰值位置误差={row['PeakPositionError']:.2f} m, "
                f"峰值强度误差={row['PeakIntensityError']:.3f}, "
                f"IoU={row['IoU']:.3f}, Dice={row['Dice']:.3f}"
            )
            lines.append("")

    scope_rows = accuracy_report
    if "field" in accuracy_report.columns:
        scope_rows = accuracy_report[accuracy_report["field"] == "smoothed"]
    for _, row in scope_rows.iterrows():
        if row["scope"] == "spatial":
            continue
        lines.append(
            f"{row['scope']}: RMSE={row['RMSE']:.4f} "
            f"MAE={row['MAE']:.4f} R2={row['R2']:.4f}"
        )
    return "\n".join(lines).strip()
