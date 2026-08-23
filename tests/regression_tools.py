"""数值回归测试共用工具：固定种子合成数据集、模型训练与黄金快照提取。

设计要点（与容差策略相关）：
- 数据集固定为 20×20（对齐窗口特征数 400 ≤ 500），使 sklearn PCA 的
  svd_solver='auto' 走 full SVD（LAPACK 确定性路径），避开 randomized
  SVD 的随机性——因此无需修改模型算法即可获得可复现数值；
- 合成场由固定种子的 PCG64 生成器加入噪声，跨平台/跨 numpy 版本流稳定；
- 快照只保存低维摘要（统计量 + 采样像素 + 指标），不保存整场。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import dataclasses  # noqa: E402

from damage_gui.config import CONFIG  # noqa: E402
from damage_gui.data.loader import Condition, DamageDataManager  # noqa: E402
from damage_gui.evaluation.metrics import extract_core_metrics  # noqa: E402
from damage_gui.model.bundle import DamageModelService  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parent / "data" / "regression_golden.json"
DATASET_SEED = 20260823
SHAPE = (20, 20)
H_VALUES = (1.0, 2.0, 3.0)
V_VALUES = (100.0, 150.0, 200.0)
DEG_VALUES = (10.0, 20.0, 30.0)
PROBES = (
    ("p1", 2.0, 160.0, 24.0),
    ("p2", 1.5, 120.0, 12.0),
    ("p3", 2.5, 190.0, 28.0),
)
SAMPLE_INDICES = tuple(range(0, SHAPE[0] * SHAPE[1], 37))  # 11 个采样像素


def regression_config():
    """数值回归专用配置：20×20 网格 + 轻评估平滑。"""
    return dataclasses.replace(
        CONFIG, target_shape=SHAPE, eval_smoothing_sigma=1.0
    )


def _synthetic_matrix(h: float, v: float, deg: float, noise: np.ndarray) -> np.ndarray:
    """幅值/宽度随工况变化 + 固定噪声扰动的中心高斯场。"""
    rows, cols = np.meshgrid(
        np.arange(SHAPE[0], dtype=float), np.arange(SHAPE[1], dtype=float),
        indexing="ij",
    )
    center_row = 9.5 + (h - 2.0) * 0.8 + noise[0]
    center_col = 9.5 + (deg - 20.0) * 0.05 + noise[1]
    sigma = 2.0 + 0.004 * v + 0.02 * deg + noise[2]
    amplitude = (
        0.35 + 0.08 * h + 0.0004 * v + 0.003 * deg + 0.05 * noise[3]
    )
    dr = rows - center_row
    dc = cols - center_col
    field = amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * sigma * sigma))
    return np.clip(field, 0.0, 1.0).astype(np.float64)


def build_regression_dataset(directory: Path) -> None:
    """写出固定种子的合成 DamageMatrix 数据集（27 工况 × 20×20）。"""
    rng = np.random.default_rng(DATASET_SEED)
    for h in H_VALUES:
        for v in V_VALUES:
            for deg in DEG_VALUES:
                noise = rng.normal(0.0, 1.0, size=4) * np.array(
                    [0.3, 0.3, 0.05, 1.0]
                )
                matrix = _synthetic_matrix(h, v, deg, noise)
                name = (
                    f"DamageMatrix_F_h_{int(h * 10)}"
                    f"_v_{int(v * 10)}_deg_{int(deg * 10)}"
                )
                lines = ["synthetic_header"]
                for row in matrix:
                    lines.append("\t".join(f"{value:.6f}" for value in row))
                (directory / name).write_text(
                    "\n".join(lines) + "\n", encoding="gbk"
                )


def make_regression_service(directory: Path) -> DamageModelService:
    return DamageModelService(
        DamageDataManager(directory), config=regression_config()
    )


def _probe_snapshot(prediction: np.ndarray) -> dict[str, Any]:
    flat = prediction.astype(np.float64).ravel()
    return {
        "max": float(flat.max()),
        "mean": float(flat.mean()),
        "sum": float(flat.sum()),
        "samples": [float(flat[i]) for i in SAMPLE_INDICES],
    }


def build_snapshot(service: DamageModelService) -> dict[str, Any]:
    """训练 RBF + POD-RBF 并提取低维数值快照（黄金值的唯一来源）。"""
    rbf_bundle = service.train_bundle(
        "F", validation_mode="random", model_type="rbf"
    )
    pod_bundle = service.train_bundle(
        "F", validation_mode="random", model_type="pod_rbf",
        pod_n_components=5,
    )

    snapshot: dict[str, Any] = {"schema": 1, "seed": DATASET_SEED}
    for key, bundle in (("rbf", rbf_bundle), ("pod_rbf", pod_bundle)):
        probes = {}
        for name, h, v, deg in PROBES:
            prediction = bundle.model.predict_matrix(Condition(h, v, deg))
            probes[name] = _probe_snapshot(prediction)
        mean_re, p95 = extract_core_metrics(
            bundle.accuracy_report, bundle.resolved_config()
        )
        section: dict[str, Any] = {"probes": probes}
        if mean_re is not None:
            section["core_metrics"] = {
                "mean_relative_error": float(mean_re),
                "p95_hybrid_error": float(p95),
            }
        if getattr(bundle.model, "explained_variance", None):
            section["explained_variance"] = float(bundle.model.explained_variance)
            section["n_components_used"] = int(bundle.model.n_components_used)
        snapshot[key] = section

    detector = rbf_bundle.ood_detector
    assert detector is not None and detector.is_fitted
    ood = {}
    for name, h, v, deg in PROBES:
        report = detector.report(Condition(h, v, deg))
        ood[name] = {"distance": float(report.distance), "level": report.level}
    snapshot["ood"] = ood
    return snapshot


def build_snapshot_in_tempdir() -> tuple[dict[str, Any], tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    build_regression_dataset(Path(tmp.name))
    service = make_regression_service(Path(tmp.name))
    return build_snapshot(service), tmp
