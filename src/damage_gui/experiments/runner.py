"""消融实验框架（M3.1）：对现有训练管线的薄封装。

给定一组 :class:`ExperimentSpec`（模型类型 × 验证策略 × 参数覆盖），
逐个调用 ``DamageModelService.train_bundle`` 并收集统一指标：

- 数值指标（主要毁伤区）：Smoothed 与 Raw 双口径的
  MeanRE / P95 混合误差 / R² / MAE（主口径为 Smoothed，见 P0-2）；
- 空间指标（Raw 场）：质心误差、峰值位置/强度误差、IoU、Dice；
- 追溯信息：git commit、训练数据指纹、随机种子、时间戳；
- POD 附加：累计解释方差（EV）与实际保留模态数，支撑 K/EV 扫描。

"四模型象限" 指 {RBF, POD-RBF} × {质心对齐开/关} 的 2×2 设计矩阵，
分别回答验收问题"为什么使用质心对齐"与"为什么使用 POD"；
双边滤波降噪的贡献维度由 scripts/ablation_study.py 覆盖，此处不重复。

M3.2 基线（最近邻 / 逐像素线性插值）与上述象限使用同一验证切分与
双口径指标，直接回答"RBF 家族相对平凡插值器赚了多少"。线性基线
只在训练工况凸包内有定义，其结果必须连同 ``extrapolation_fraction``
（触发凸包外最近邻回填的预测比例）一起解读。

单个实验失败（如验证切分对当前数据不适用）记录为 ``status="error"``
并写明原因，不中断整个套件——不适用的结论也是结论。
"""
from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from damage_gui.config import Config
from damage_gui.model.validation import VALIDATION_MODES

if TYPE_CHECKING:
    # 延迟到运行时导入：bundle 会导入本包（基线模型），顶层互引会成环
    from damage_gui.model.bundle import DamageModelService


@dataclass(frozen=True)
class ExperimentSpec:
    """一次实验配置：模型类型 + 验证策略 + Config 字段覆盖。"""

    name: str
    model_type: str = "rbf"  # "rbf" | "pod_rbf" | "nn" | "linear"
    validation_mode: str = "random"
    config_overrides: dict[str, Any] = field(default_factory=dict)
    pod_n_components: int | None = None
    notes: str = ""


@dataclass(frozen=True)
class ExperimentResult:
    """一次实验的完整记录：配置快照 + 指标 + 追溯信息。"""

    experiment: str
    suite: str
    level: str
    model_type: str
    validation_mode: str
    # 配置快照（覆盖后的实际取值）
    align_patterns: bool
    rbf_kernel: str
    rbf_smoothing: float
    rbf_epsilon: float | None
    pod_n_components: int | None
    seed: int
    # 结果
    status: str  # "ok" | "error"
    error: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    train_time_seconds: float | None = None
    explained_variance: float | None = None
    n_components_used: int | None = None
    # 线性基线：评估预测中落在训练工况凸包外的比例（其余模型为 None）
    extrapolation_fraction: float | None = None
    training_samples: int | None = None
    git_commit: str | None = None
    training_data_hash: str | None = None
    timestamp: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """扁平化为可序列化行（NaN → None），供 CSV/JSON 输出。"""
        row: dict[str, Any] = {
            "suite": self.suite,
            "experiment": self.experiment,
            "level": self.level,
            "model_type": self.model_type,
            "validation_mode": self.validation_mode,
            "align_patterns": self.align_patterns,
            "rbf_kernel": self.rbf_kernel,
            "rbf_smoothing": self.rbf_smoothing,
            "rbf_epsilon": self.rbf_epsilon,
            "pod_n_components": self.pod_n_components,
            "seed": self.seed,
            "status": self.status,
            "error": self.error,
            "train_time_seconds": self.train_time_seconds,
            "explained_variance": self.explained_variance,
            "n_components_used": self.n_components_used,
            "extrapolation_fraction": self.extrapolation_fraction,
            "training_samples": self.training_samples,
            "git_commit": self.git_commit,
            "training_data_hash": self.training_data_hash,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }
        for key, value in self.metrics.items():
            row[key] = _clean(value)
        return row


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _focus_metrics(accuracy_report: pd.DataFrame, config: Config) -> dict[str, float]:
    """从训练报告中抽取双口径核心指标与空间指标。"""
    out: dict[str, float] = {}
    focus_scope = f"damage_gt_{config.relative_error_threshold:.2f}"
    for field_name in ("smoothed", "raw"):
        prefix = "" if field_name == "smoothed" else "raw_"
        sel = accuracy_report[
            (accuracy_report["scope"] == focus_scope)
            & (accuracy_report["field"] == field_name)
        ]
        if sel.empty:
            continue
        row = sel.iloc[0]
        out[f"{prefix}mean_relative_error"] = float(row["MeanRelativeError"])
        out[f"{prefix}p95_hybrid_error"] = float(row["P95HybridError"])
        out[f"{prefix}r2"] = float(row["R2"])
        out[f"{prefix}mae"] = float(row["MAE"])
    spatial = accuracy_report[accuracy_report["scope"] == "spatial"]
    if not spatial.empty:
        row = spatial.iloc[0]
        out["centroid_error_m"] = float(row["CentroidError"])
        out["peak_position_error_m"] = float(row["PeakPositionError"])
        out["peak_intensity_error"] = float(row["PeakIntensityError"])
        out["iou"] = float(row["IoU"])
        out["dice"] = float(row["Dice"])
    return out


def run_experiment(
    service: DamageModelService,
    level: str,
    spec: ExperimentSpec,
    *,
    config: Config | None = None,
    suite: str = "",
) -> ExperimentResult:
    """执行单个实验；失败时抛异常，由 :func:`run_suite` 统一兜底。"""
    from damage_gui.model.bundle import DamageModelService  # 见模块头注释

    config = config or dataclasses.replace(service.config, **spec.config_overrides)
    scoped = DamageModelService(service.data_manager, config=config)
    bundle = scoped.train_bundle(
        level,
        validation_mode=spec.validation_mode,
        model_type=spec.model_type,
        pod_n_components=spec.pod_n_components,
    )
    metadata = bundle.metadata
    return ExperimentResult(
        experiment=spec.name,
        suite=suite,
        level=level,
        model_type=spec.model_type,
        validation_mode=spec.validation_mode,
        align_patterns=config.align_patterns,
        rbf_kernel=config.rbf_kernel,
        rbf_smoothing=config.rbf_smoothing,
        rbf_epsilon=config.rbf_epsilon,
        pod_n_components=(
            spec.pod_n_components or config.pod_n_components
            if spec.model_type == "pod_rbf"
            else None
        ),
        seed=config.random_state,
        status="ok",
        metrics=_focus_metrics(bundle.accuracy_report, config),
        train_time_seconds=bundle.train_time_seconds,
        explained_variance=_optional_float(bundle.model, "explained_variance"),
        n_components_used=_optional_int(bundle.model, "n_components_used"),
        extrapolation_fraction=bundle.test_extrapolation_fraction,
        training_samples=len(bundle.train_conditions),
        git_commit=getattr(metadata, "code_commit", None),
        training_data_hash=getattr(metadata, "training_data_hash", None),
        timestamp=_utc_now_iso(),
        notes=spec.notes,
    )


def _optional_float(model: Any, attr: str) -> float | None:
    value = getattr(model, attr, None)
    return None if value is None else float(value)


def _optional_int(model: Any, attr: str) -> int | None:
    value = getattr(model, attr, None)
    return None if value is None else int(value)


def _failure_result(
    spec: ExperimentSpec,
    suite: str,
    level: str,
    config: Config,
    exc: Exception,
) -> ExperimentResult:
    return ExperimentResult(
        experiment=spec.name,
        suite=suite,
        level=level,
        model_type=spec.model_type,
        validation_mode=spec.validation_mode,
        align_patterns=config.align_patterns,
        rbf_kernel=config.rbf_kernel,
        rbf_smoothing=config.rbf_smoothing,
        rbf_epsilon=config.rbf_epsilon,
        pod_n_components=(
            spec.pod_n_components or config.pod_n_components
            if spec.model_type == "pod_rbf"
            else None
        ),
        seed=config.random_state,
        status="error",
        error=f"{type(exc).__name__}: {exc}",
        timestamp=_utc_now_iso(),
        notes=spec.notes,
    )


def run_suite(
    service: DamageModelService,
    level: str,
    specs: list[ExperimentSpec],
    *,
    suite: str = "",
) -> list[ExperimentResult]:
    """顺序执行实验套件；单实验失败记录为 error 结果并继续。"""
    results: list[ExperimentResult] = []
    for spec in specs:
        try:
            config = dataclasses.replace(service.config, **spec.config_overrides)
        except TypeError as exc:  # 未知配置键：配置错误不应静默
            results.append(_failure_result(spec, suite, level, service.config, exc))
            continue
        try:
            results.append(
                run_experiment(service, level, spec, config=config, suite=suite)
            )
        except Exception as exc:  # 数据不适用/数值失败：如实记录，不中断套件
            results.append(_failure_result(spec, suite, level, config, exc))
    return results


# ===================== 预设实验矩阵 =====================

def design_quadrant_specs() -> list[ExperimentSpec]:
    """四模型象限：{RBF, POD-RBF} × {质心对齐 关/开}，其余配置取当前默认。"""
    specs: list[ExperimentSpec] = []
    for model_type in ("rbf", "pod_rbf"):
        for align in (False, True):
            specs.append(
                ExperimentSpec(
                    name=f"{model_type}_align={'on' if align else 'off'}",
                    model_type=model_type,
                    validation_mode="random",
                    config_overrides={"align_patterns": align},
                    notes="设计象限：模型类型 × 质心对齐",
                )
            )
    return specs


def baseline_specs() -> list[ExperimentSpec]:
    """M3.2 基线：最近邻 + 逐像素线性插值（随机留出，与象限同口径对比）。

    线性基线仅在训练工况凸包内有定义，其指标必须连同结果中的
    ``extrapolation_fraction``（凸包外回填比例）一起解读。
    """
    return [
        ExperimentSpec(
            name="baseline_nn",
            model_type="nn",
            validation_mode="random",
            notes="基线：最近邻",
        ),
        ExperimentSpec(
            name="baseline_linear",
            model_type="linear",
            validation_mode="random",
            notes="基线：逐像素线性插值（凸包外最近邻回填）",
        ),
    ]


def validation_specs(model_type: str = "pod_rbf") -> list[ExperimentSpec]:
    """验证策略对比：随机留出 + 三种整层留出 + 角落外推。"""
    return [
        ExperimentSpec(
            name=f"validation_{mode}",
            model_type=model_type,
            validation_mode=mode,
            notes="验证策略对比",
        )
        for mode in VALIDATION_MODES
    ]


def pod_sweep_specs(
    ks: tuple[int, ...] = (5, 10, 15, 20, 25, 30),
) -> list[ExperimentSpec]:
    """POD 模态数 K 扫描；结果行附累计解释方差（EV）供 K-误差权衡分析。"""
    return [
        ExperimentSpec(
            name=f"pod_K={k}",
            model_type="pod_rbf",
            validation_mode="random",
            pod_n_components=k,
            notes="POD K 扫描",
        )
        for k in ks
    ]


def rbf_param_specs(
    kernels: tuple[str, ...] = ("thin_plate_spline", "multiquadric"),
    smoothings: tuple[float, ...] = (0.0, 1e-3),
    epsilons: tuple[float | None, ...] = (None,),
) -> list[ExperimentSpec]:
    """RBF 核 × 平滑 × epsilon 网格（epsilon 仅对支持的核生效）。"""
    specs: list[ExperimentSpec] = []
    for kernel in kernels:
        for smoothing in smoothings:
            for epsilon in epsilons:
                label = f"rbf_{kernel}_s={smoothing:g}"
                if epsilon is not None:
                    label += f"_e={epsilon:g}"
                specs.append(
                    ExperimentSpec(
                        name=label,
                        model_type="rbf",
                        validation_mode="random",
                        config_overrides={
                            "rbf_kernel": kernel,
                            "rbf_smoothing": smoothing,
                            "rbf_epsilon": epsilon,
                        },
                        notes="RBF 参数扫描",
                    )
                )
    return specs


# ===================== 报告输出 =====================

# Markdown 摘要表精选列（全量列见 CSV/JSON）
_MD_COLUMNS = (
    ("experiment", "Experiment"),
    ("status", "Status"),
    ("model_type", "Model"),
    ("validation_mode", "Validation"),
    ("align_patterns", "Align"),
    ("pod_n_components", "K"),
    ("mean_relative_error", "MeanRE(sm)"),
    ("p95_hybrid_error", "P95(sm)"),
    ("r2", "R2(sm)"),
    ("raw_mean_relative_error", "MeanRE(raw)"),
    ("dice", "Dice"),
    ("iou", "IoU"),
    ("centroid_error_m", "CentroidErr(m)"),
    ("extrapolation_fraction", "Extrap%"),
    ("train_time_seconds", "Train(s)"),
)


def _format_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        if abs(value) < 1.0:
            return f"{value:.4f}"
        return f"{value:.2f}"
    return str(value)


def save_report(
    results: list[ExperimentResult],
    out_dir: str | Path,
    name: str,
    *,
    level: str | None = None,
    data_dir: str | Path | None = None,
) -> dict[str, Path]:
    """写出 CSV（全量列）+ JSON（机器可读）+ Markdown（摘要表）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [result.to_dict() for result in results]
    frame = pd.DataFrame(rows)

    csv_path = out / f"{name}.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    generated_at = _utc_now_iso()
    payload = {
        "name": name,
        "level": level or (results[0].level if results else None),
        "data_dir": None if data_dir is None else str(data_dir),
        "generated_at": generated_at,
        "seed": results[0].seed if results else None,
        "git_commit": next((r.git_commit for r in results if r.git_commit), None),
        "training_data_hash": next(
            (r.training_data_hash for r in results if r.training_data_hash), None
        ),
        "n_results": len(rows),
        "n_errors": sum(1 for r in results if r.status == "error"),
        "results": rows,
    }
    json_path = out / f"{name}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# 实验报告：{name}",
        "",
        f"- 生成时间（UTC）: {generated_at}",
        f"- 数据目录: {payload['data_dir'] or '—'}",
        f"- 等级: {payload['level'] or '—'} | 随机种子: {payload['seed']}",
        f"- 代码 commit: {payload['git_commit'] or '—'}",
        f"- 训练数据指纹: {payload['training_data_hash'] or '—'}",
        "",
    ]
    if rows:
        header = " | ".join(title for _key, title in _MD_COLUMNS)
        lines += [f"| {header} |", "|" + "---|" * len(_MD_COLUMNS)]
        for row in rows:
            cells = " | ".join(_format_cell(row.get(key)) for key, _t in _MD_COLUMNS)
            lines.append(f"| {cells} |")
        errors = [row for row in rows if row["status"] == "error"]
        if errors:
            lines += ["", "## 失败/不适用的实验", ""]
            for row in errors:
                lines.append(f"- **{row['experiment']}**: {row['error']}")
    else:
        lines.append("（无实验结果）")
    md_path = out / f"{name}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"csv": csv_path, "json": json_path, "md": md_path}
