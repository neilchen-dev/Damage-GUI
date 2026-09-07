"""样本级预测不确定度估计与校准验证（M3.4）。

轻量化路线（不训练第二套模型）：

- LOO 残差：对每个训练工况做留一法（用其余工况训练、预测该工况），
  以 Smoothed 口径下的 ROI MAE 作为该样本的残差；
- 对新查询工况给出两种无需重训的估计：
  * ``knn_distance``：归一化工况空间中到第 k 近训练工况的距离
    （排序口径，只考察与误差的单调关系）；
  * ``residual_knn``：k 个最近训练工况残差的均值（与误差同量纲，
    可直接做数值校准）。

校准验证：Spearman 秩相关 + 分位数校准分箱表 + 可靠性曲线图。
Bootstrap 残差需要 smoothing>0 的 B 次重训，代价 O(B×训练) 且引入
随机性，与 M3.4 的轻量定位不符，未采用；报告中如实说明。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from damage_gui.config import Config
from damage_gui.data.loader import Condition, DamageRecord, read_damage_matrix
from damage_gui.data.preprocessing import evaluation_fields, roi_mask_for_shape
from damage_gui.model.bundle import DamageModelService, build_model


def sample_roi_mae(
    true_matrix: np.ndarray, pred_matrix: np.ndarray, config: Config
) -> float:
    """单样本误差：Smoothed 口径（与训练评估一致）下的 ROI MAE。"""
    smoothed_true, smoothed_pred = evaluation_fields(true_matrix, pred_matrix, config)
    roi = roi_mask_for_shape(true_matrix.shape, config)
    return float(np.abs(smoothed_true - smoothed_pred)[roi].mean())


def loo_residuals(
    service: DamageModelService,
    level: str,
    model_type: str = "rbf",
) -> tuple[list[DamageRecord], np.ndarray]:
    """逐工况留一法预测，返回记录列表与每个样本的残差。"""
    config = service.config
    records = service.data_manager.get_level_records(level)
    conditions = np.array(
        [record.condition.as_array() for record in records], dtype=np.float64
    )
    matrices = np.stack([read_damage_matrix(record.path, config) for record in records])

    residuals = np.zeros(len(records), dtype=np.float64)
    for i in range(len(records)):
        mask = np.ones(len(records), dtype=bool)
        mask[i] = False
        model = build_model(model_type, config)
        model.fit(conditions[mask], matrices[mask])
        pred = model.predict_matrix(records[i].condition)
        residuals[i] = sample_roi_mae(matrices[i], pred, config)
    return records, residuals


class UncertaintyEstimator:
    """基于训练工况的 kNN 不确定度估计器（归一化空间，与模型口径一致）。"""

    def __init__(self, conditions: np.ndarray, residuals: np.ndarray, k: int = 3):
        conditions = np.asarray(conditions, dtype=np.float64)
        lo = conditions.min(axis=0)
        hi = conditions.max(axis=0)
        self._lo = lo
        # 归一化尺度防护：span 为 denormal/极小值时，归一化会把查询坐标放大到
        # 1e200+ 量级，norm 平方溢出为 inf。下限只影响归一化尺度本身，不改数据
        # 与距离定义；真实工况网格（文件名 0.1 量化，span ≥ 0.1）恒为 no-op。
        self._span = np.where(hi - lo > 1e-12, hi - lo, 1.0)
        self._points = (conditions - self._lo) / self._span
        self.residuals = np.asarray(residuals, dtype=np.float64)
        self.k = k

    def _distances(self, condition: Condition) -> np.ndarray:
        query = (condition.as_array() - self._lo) / self._span
        return np.linalg.norm(self._points - query, axis=1)

    def knn_distance(self, condition: Condition) -> float:
        """到第 k 近训练工况的距离（排序口径）。"""
        kth = min(self.k, len(self._points)) - 1
        return float(np.sort(self._distances(condition))[kth])

    def residual_knn(self, condition: Condition) -> float:
        """k 个最近训练工况残差的均值（与误差同量纲）。"""
        order = np.argsort(self._distances(condition))
        return float(self.residuals[order[: min(self.k, len(order))]].mean())


def calibration_bins(
    estimates: np.ndarray, errors: np.ndarray, n_bins: int
) -> pd.DataFrame:
    """按估计值分位数分箱，给出每箱的估计/误差均值（可靠性曲线数据）。"""
    quantiles = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.unique(np.quantile(estimates, quantiles))
    if len(edges) < 3:  # 估计值几乎无区分度时退化为单箱，如实呈现
        return pd.DataFrame(
            [{"bin": 0, "n": len(errors), "mean_estimate": float(estimates.mean()),
              "mean_error": float(errors.mean())}]
        )
    index = np.clip(
        np.searchsorted(edges, estimates, side="right") - 1, 0, len(edges) - 2
    )
    rows = []
    for bin_id in range(len(edges) - 1):
        sel = index == bin_id
        if not np.any(sel):
            continue
        rows.append(
            {
                "bin": bin_id,
                "n": int(sel.sum()),
                "mean_estimate": float(estimates[sel].mean()),
                "mean_error": float(errors[sel].mean()),
            }
        )
    return pd.DataFrame(rows)


def _spearman(estimates: np.ndarray, errors: np.ndarray) -> float:
    if len(np.unique(estimates)) < 2 or len(np.unique(errors)) < 2:
        return float("nan")  # 常量输入无秩信息，相关系数无定义
    rho, _ = spearmanr(estimates, errors)
    return float(rho) if np.isfinite(rho) else float("nan")


def run_uncertainty_study(
    service: DamageModelService,
    level: str,
    *,
    model_type: str = "rbf",
    k: int = 3,
    n_bins: int = 4,
) -> dict[str, Any]:
    """LOO 残差 + 双估计器的留一校准研究。

    对样本 i 的估计只用其余样本构建（与研究对象本身同样留一），
    避免自校准造成的虚高。
    """
    records, residuals = loo_residuals(service, level, model_type)
    conditions = np.array(
        [record.condition.as_array() for record in records], dtype=np.float64
    )

    rows = []
    for i, record in enumerate(records):
        others = np.arange(len(records)) != i
        estimator = UncertaintyEstimator(
            conditions[others], residuals[others], k=k
        )
        rows.append(
            {
                "h": record.condition.h,
                "v": record.condition.v,
                "deg": record.condition.deg,
                "error": float(residuals[i]),
                "est_distance": estimator.knn_distance(record.condition),
                "est_residual_knn": estimator.residual_knn(record.condition),
            }
        )
    frame = pd.DataFrame(rows)

    errors = frame["error"].to_numpy()
    summary: dict[str, Any] = {
        "level": level,
        "model_type": model_type,
        "n_samples": len(records),
        "k": k,
        "error_mean": float(errors.mean()),
        "spearman_distance": _spearman(frame["est_distance"].to_numpy(), errors),
        "spearman_residual_knn": _spearman(
            frame["est_residual_knn"].to_numpy(), errors
        ),
    }
    bins = {
        "distance": calibration_bins(frame["est_distance"].to_numpy(), errors, n_bins),
        "residual_knn": calibration_bins(
            frame["est_residual_knn"].to_numpy(), errors, n_bins
        ),
    }
    return {"summary": summary, "samples": frame, "bins": bins}


def plot_reliability(bins: pd.DataFrame, path: str | Path, title: str) -> Path:
    """可靠性曲线：分箱均值估计 vs 分箱均值误差（对角线 = 完美校准）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(path)
    figure, axis = plt.subplots(figsize=(4.2, 4.2), dpi=120)
    axis.plot(
        bins["mean_estimate"], bins["mean_error"], marker="o", color="#1E3A8A"
    )
    limit = max(bins["mean_estimate"].max(), bins["mean_error"].max()) * 1.05
    axis.plot([0, limit], [0, limit], linestyle="--", color="#64748B", linewidth=1)
    axis.set_xlabel("Mean estimated uncertainty")
    axis.set_ylabel("Mean actual error (ROI MAE, smoothed)")
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    return path


def save_uncertainty_report(
    study: dict[str, Any],
    out_dir: str | Path,
    name: str,
    *,
    data_dir: str | Path | None = None,
) -> dict[str, Path]:
    """CSV（逐样本）+ JSON（摘要+分箱）+ MD + 可靠性曲线 PNG。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = study["summary"]
    samples: pd.DataFrame = study["samples"]

    csv_path = out / f"{name}.csv"
    samples.to_csv(csv_path, index=False, encoding="utf-8-sig")

    png_path = plot_reliability(
        study["bins"]["residual_knn"],
        out / f"{name}_reliability.png",
        f"Reliability ({summary['model_type']}, level {summary['level']})",
    )

    payload = {
        "name": name,
        "data_dir": None if data_dir is None else str(data_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "bins": {
            key: frame.to_dict(orient="records")
            for key, frame in study["bins"].items()
        },
    }
    json_path = out / f"{name}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    def _fmt(value: Any) -> str:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return "—"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    lines = [
        f"# 不确定度校准报告：{name}",
        "",
        f"- 生成时间（UTC）: {payload['generated_at']}",
        f"- 数据目录: {payload['data_dir'] or '—'} | 等级: {summary['level']}"
        f" | 模型: {summary['model_type']} | 样本数: {summary['n_samples']}"
        f" | k: {summary['k']}",
        f"- 样本平均误差（Smoothed ROI MAE）: {_fmt(summary['error_mean'])}",
        "",
        "## Spearman 秩相关（估计值 vs 实际误差）",
        "",
        f"- knn_distance（排序口径）: {_fmt(summary['spearman_distance'])}",
        f"- residual_knn（同量纲）: {_fmt(summary['spearman_residual_knn'])}",
        "",
        "## 校准分箱（residual_knn，同量纲）",
        "",
        "| bin | n | mean_estimate | mean_error |",
        "|---|---|---|---|",
    ]
    for row in study["bins"]["residual_knn"].to_dict(orient="records"):
        lines.append(
            f"| {row['bin']} | {row['n']} | {_fmt(row['mean_estimate'])} "
            f"| {_fmt(row['mean_error'])} |"
        )
    lines += [
        "",
        "## 校准分箱（knn_distance，排序口径）",
        "",
        "| bin | n | mean_estimate | mean_error |",
        "|---|---|---|---|",
    ]
    for row in study["bins"]["distance"].to_dict(orient="records"):
        lines.append(
            f"| {row['bin']} | {row['n']} | {_fmt(row['mean_estimate'])} "
            f"| {_fmt(row['mean_error'])} |"
        )
    lines += [
        "",
        f"可靠性曲线: {png_path.name}",
        "",
        "方法说明：LOO 残差（Smoothed 口径 ROI MAE）+ kNN 估计；"
        "对样本 i 的估计只用其余样本构建。Bootstrap 残差需 B 次重训，"
        "与轻量定位不符，未采用。若相关系数接近 0 或分箱无单调趋势，"
        "说明该估计器对当前数据不可靠，应如实报告而非调参掩盖。",
    ]
    md_path = out / f"{name}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"csv": csv_path, "json": json_path, "md": md_path, "png": png_path}
