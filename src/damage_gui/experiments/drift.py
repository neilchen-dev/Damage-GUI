"""轻量输入分布漂移（Drift）检测（M3.8）。

回答一个问题：新到来的查询工况分布，是否偏离模型训练工况分布？
只比较输入工况 (h, v, deg)，不重训模型、不碰预测管线：

- 逐维两样本 KS 检验（训练分布 vs 查询分布），p < alpha 记为漂移；
- 归一化工况空间中查询到最近训练工况的距离（与 OOD 同一口径），
  给出均值与超过 ``ood_medium_max``（外推阈值）的查询比例；
- 逐维范围覆盖：查询值落在训练 [min, max] 之外的计数。

诚实局限：训练工况通常只有几十个，KS 检验功效有限，小偏移测不出；
但大范围偏移与越界查询（硬外推）能被 KS、范围覆盖与最近邻距离
三方交叉确认。结论应连同样本量一起解读。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from damage_gui.config import Config
from damage_gui.errors import DataValidationError

DIMENSIONS = ("h", "v", "deg")


def _conditions_frame(records) -> pd.DataFrame:
    return pd.DataFrame(
        [record.condition.as_dict() for record in records],
        columns=list(DIMENSIONS),
    )


def load_query_conditions(path: str | Path) -> np.ndarray:
    """解析查询工况 CSV：必须含 h/v/deg 三列，行级非法值直接拒绝。"""
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise DataValidationError(f"查询工况 CSV 不可读: {exc}") from exc
    missing = [name for name in DIMENSIONS if name not in frame.columns]
    if missing:
        raise DataValidationError(f"查询工况 CSV 缺少列: {missing}")
    values = frame[list(DIMENSIONS)]
    if not values.apply(pd.to_numeric, errors="coerce").notna().all().all():
        raise DataValidationError("查询工况 CSV 存在非数值或缺失的 h/v/deg")
    return values.to_numpy(dtype=np.float64)


def drift_report(
    train_conditions: np.ndarray,
    query_conditions: np.ndarray,
    config: Config,
    *,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """训练分布 vs 查询分布的漂移报告（纯统计，无模型调用）。"""
    train = np.asarray(train_conditions, dtype=np.float64)
    queries = np.asarray(query_conditions, dtype=np.float64)
    if train.ndim != 2 or train.shape[1] != 3:
        raise DataValidationError("训练工况应为 (n, 3) 数组")
    if queries.ndim != 2 or queries.shape[1] != 3:
        raise DataValidationError("查询工况应为 (n, 3) 数组")
    if len(train) < 2:
        raise DataValidationError("训练工况少于 2 个，无法做分布比较")
    if len(queries) == 0:
        raise DataValidationError("查询工况为空，无法做漂移检测")

    lo = train.min(axis=0)
    hi = train.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)

    dimensions: dict[str, Any] = {}
    for axis, name in enumerate(DIMENSIONS):
        statistic, pvalue = ks_2samp(train[:, axis], queries[:, axis])
        train_lo, train_hi = float(lo[axis]), float(hi[axis])
        col = queries[:, axis]
        dimensions[name] = {
            "ks_statistic": round(float(statistic), 6),
            "p_value": round(float(pvalue), 6),
            "drift": bool(pvalue < alpha),
            "train_range": [train_lo, train_hi],
            "query_range": [float(col.min()), float(col.max())],
            "out_of_range": int(((col < train_lo) | (col > train_hi)).sum()),
        }

    train_norm = (train - lo) / span
    query_norm = (queries - lo) / span
    distances = np.array([
        float(np.linalg.norm(train_norm - q, axis=1).min()) for q in query_norm
    ])
    extrapolation = distances >= config.ood_medium_max

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alpha": alpha,
        "n_train": int(len(train)),
        "n_queries": int(len(queries)),
        "dimensions": dimensions,
        "nearest_distance": {
            "mean": round(float(distances.mean()), 6),
            "p95": round(float(np.quantile(distances, 0.95)), 6),
            "max": round(float(distances.max()), 6),
            "extrapolation_threshold": float(config.ood_medium_max),
            "extrapolation_fraction": round(float(extrapolation.mean()), 6),
        },
        "drift_detected": any(item["drift"] for item in dimensions.values()),
    }


def verdict_line(report: dict[str, Any]) -> str:
    """单行结论（CLI/日志共用）。"""
    drifted = [name for name, item in report["dimensions"].items() if item["drift"]]
    nn = report["nearest_distance"]
    if drifted:
        status = f"检测到漂移（{'、'.join(drifted)} 维 KS p<{report['alpha']}）"
    else:
        status = "未检测到显著漂移"
    return (
        f"{status} | 外推查询比例 {nn['extrapolation_fraction']:.1%}"
        f"（阈值 {nn['extrapolation_threshold']}）"
        f" | 最近训练工况距离均值 {nn['mean']:.3f} / P95 {nn['p95']:.3f}"
    )


def save_drift_report(
    report: dict[str, Any],
    out_dir: str | Path,
    name: str,
    *,
    level: str,
) -> dict[str, Path]:
    """JSON（机器可读）+ MD（人读摘要）落盘。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "level": level, **report}

    json_path = out / f"{name}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# 输入分布漂移报告：{name}（等级 {level}）",
        "",
        f"- 生成时间（UTC）: {report['generated_at']}",
        f"- 训练工况数: {report['n_train']} | 查询工况数: {report['n_queries']}"
        f" | 显著性水平: {report['alpha']}",
        f"- 结论: {verdict_line(report)}",
        "",
        "## 逐维 KS 检验（训练分布 vs 查询分布）",
        "",
        "| 维度 | KS 统计量 | p 值 | 漂移 | 训练范围 | 查询范围 | 越界数 |",
        "|---|---|---|---|---|---|---|",
    ]
    for name_, item in report["dimensions"].items():
        train_lo, train_hi = item["train_range"]
        query_lo, query_hi = item["query_range"]
        lines.append(
            f"| {name_} | {item['ks_statistic']:.4f} | {item['p_value']:.4f} "
            f"| {'是' if item['drift'] else '否'} "
            f"| [{train_lo:.1f}, {train_hi:.1f}] "
            f"| [{query_lo:.1f}, {query_hi:.1f}] | {item['out_of_range']} |"
        )
    nn = report["nearest_distance"]
    lines += [
        "",
        "## 最近训练工况距离（归一化工况空间，与 OOD 同口径）",
        "",
        f"- 均值: {nn['mean']:.4f} | P95: {nn['p95']:.4f} | 最大: {nn['max']:.4f}",
        f"- 外推阈值（ood_medium_max）: {nn['extrapolation_threshold']}"
        f"，超过阈值的查询比例: {nn['extrapolation_fraction']:.1%}",
        "",
        "局限说明：训练工况样本量有限时 KS 检验功效有限，小偏移可能测不出；"
        "越界查询（硬外推）以范围覆盖与最近邻距离为准。"
        "结论应连同样本量一起解读，不应只凭 p 值下结论。",
    ]
    md_path = out / f"{name}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "md": md_path}
