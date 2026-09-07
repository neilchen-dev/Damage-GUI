"""模型元数据：训练可追溯信息与三版本号管理。

三个版本号职责不同，不可混用：
- app_version          软件版本（damage_gui.__version__，随发布迭代）
- schema_version       元数据 sidecar（*.meta.json）的结构版本
- model_format_version joblib 模型包（ModelBundle 类布局）的格式版本；
                       无元数据的旧版模型包视为 0
"""
from __future__ import annotations

import hashlib
import math
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from damage_gui import __version__
from damage_gui.errors import ModelLoadError
from damage_gui.evaluation.metrics import extract_core_metrics

if TYPE_CHECKING:  # 仅类型标注使用，避免运行时反向依赖
    from damage_gui.config import Config
    from damage_gui.data.loader import DamageRecord

METADATA_SCHEMA_VERSION = 1
MODEL_FORMAT_VERSION = 1

_REQUIRED_FIELDS = (
    "model_id", "created_at", "app_version", "schema_version",
    "model_format_version", "model_type", "damage_level",
    "training_samples", "training_data_hash",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _p95_suffix(value: Any) -> str:
    """验证摘要行的 P95 后缀；缺失时留空不误导。"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"，P95混合 {value:.2%}"


def git_commit_sha() -> str | None:
    """当前代码 commit（短 SHA）；不在 Git 仓库或 Git 不可用时返回 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def training_data_hash(records: list[DamageRecord]) -> str:
    """训练数据指纹：排序后的「工况 + 源文件内容 SHA-256」列表再取 SHA-256。

    同时覆盖工况组合与文件内容，防止"文件名相同但数据被替换"的情况。
    """
    lines: list[str] = []
    for record in sorted(records, key=lambda item: item.condition.as_key()):
        try:
            file_hash = _file_sha256(record.path)
        except OSError:
            file_hash = "unreadable"
        condition = record.condition
        lines.append(
            f"{condition.h:.1f}|{condition.v:.1f}|{condition.deg:.1f}|{file_hash}"
        )
    combined = "\n".join(lines).encode("utf-8")
    return "sha256:" + hashlib.sha256(combined).hexdigest()


def _validation_summary(
    accuracy_report,
    config: Config,
    validation_mode: str,
    train_time_seconds: float,
) -> dict[str, Any]:
    """从训练产出的精度报告中提取验证摘要。

    主口径为 Smoothed（局部平均场）：历史键名
    mean_relative_error / p95_hybrid_error / r2 保持不变；
    同时并列记录 Raw（逐像素）口径的 raw_* 键，并以
    primary_field 显式标注主口径，避免单一口径被误读。
    """
    summary: dict[str, Any] = {
        "method": validation_mode,
        "primary_field": "smoothed",
        "train_time_seconds": round(float(train_time_seconds), 3),
    }
    mean_re, p95_hybrid = extract_core_metrics(accuracy_report, config)
    if mean_re is not None and not math.isnan(float(mean_re)):
        summary["mean_relative_error"] = round(float(mean_re), 6)
    if p95_hybrid is not None and not math.isnan(float(p95_hybrid)):
        summary["p95_hybrid_error"] = round(float(p95_hybrid), 6)

    raw_mean_re, raw_p95_hybrid = (
        extract_core_metrics(accuracy_report, config, field="raw")
        if "field" in accuracy_report.columns
        else (None, None)
    )
    if raw_mean_re is not None and not math.isnan(float(raw_mean_re)):
        summary["raw_mean_relative_error"] = round(float(raw_mean_re), 6)
    if raw_p95_hybrid is not None and not math.isnan(float(raw_p95_hybrid)):
        summary["raw_p95_hybrid_error"] = round(float(raw_p95_hybrid), 6)

    focus_scope = f"damage_gt_{config.relative_error_threshold:.2f}"
    for field_name, r2_key in (("smoothed", "r2"), ("raw", "raw_r2")):
        focus = accuracy_report[accuracy_report["scope"] == focus_scope]
        if "field" in accuracy_report.columns:
            focus = focus[focus["field"] == field_name]
        elif field_name != "smoothed":
            continue
        if not focus.empty:
            r2 = float(focus.iloc[0]["R2"])
            if not math.isnan(r2):
                summary[r2_key] = round(r2, 6)
    return summary


@dataclass(frozen=True)
class ModelMetadata:
    """模型元数据：随 joblib 内嵌保存，并同步写为 JSON sidecar。"""

    model_id: str
    created_at: str
    app_version: str
    schema_version: int
    model_format_version: int
    model_type: str  # "rbf" | "pod_rbf"
    damage_level: str  # "F" | "M" | "P"
    training_samples: int
    training_data_hash: str
    code_commit: str | None
    parameters: dict[str, Any]
    validation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "created_at": self.created_at,
            "app_version": self.app_version,
            "schema_version": self.schema_version,
            "model_format_version": self.model_format_version,
            "model_type": self.model_type,
            "damage_level": self.damage_level,
            "training_samples": self.training_samples,
            "training_data_hash": self.training_data_hash,
            "code_commit": self.code_commit,
            "parameters": dict(self.parameters),
            "validation": dict(self.validation),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelMetadata:
        """解析并校验元数据；schema 版本高于当前软件时给出明确错误。"""
        if not isinstance(data, dict):
            raise ModelLoadError("元数据格式不正确：应为 JSON 对象")
        missing = [key for key in _REQUIRED_FIELDS if key not in data]
        if missing:
            raise ModelLoadError(f"元数据缺少字段 {missing}，sidecar 文件可能已损坏")
        schema_version = data["schema_version"]
        if not isinstance(schema_version, int):
            raise ModelLoadError("元数据 schema_version 必须是整数")
        if schema_version > METADATA_SCHEMA_VERSION:
            raise ModelLoadError(
                f"元数据 schema 版本 {schema_version} 高于当前软件支持的 "
                f"{METADATA_SCHEMA_VERSION}，请升级 Damage-GUI 后再加载该模型"
            )
        return cls(
            model_id=str(data["model_id"]),
            created_at=str(data["created_at"]),
            app_version=str(data["app_version"]),
            schema_version=schema_version,
            model_format_version=int(data["model_format_version"]),
            model_type=str(data["model_type"]),
            damage_level=str(data["damage_level"]),
            training_samples=int(data["training_samples"]),
            training_data_hash=str(data["training_data_hash"]),
            code_commit=data.get("code_commit"),
            parameters=dict(data.get("parameters") or {}),
            validation=dict(data.get("validation") or {}),
        )

    def summary_lines(self) -> list[str]:
        """GUI/CLI 通用的中文摘要行。"""
        model_name = "POD-RBF" if self.model_type == "pod_rbf" else "RBF"
        lines = [
            f"模型 ID: {self.model_id[:8]}",
            f"软件版本: {self.app_version} | 元数据 schema: {self.schema_version}"
            f" | 模型格式: {self.model_format_version}",
            f"模型: {model_name}（等级 {self.damage_level}，"
            f"{self.training_samples} 个训练工况）",
            f"训练数据指纹: {self.training_data_hash[:19]}…",
        ]
        if self.code_commit:
            lines.append(f"训练时代码 commit: {self.code_commit}")
        validation = self.validation
        if "mean_relative_error" in validation:
            method = validation.get("method", "-")
            if "raw_mean_relative_error" in validation:
                lines.append(
                    f"验证: {method}（主口径: Smoothed 局部平均场）"
                )
                lines.append(
                    f"Smoothed: MeanRE {validation['mean_relative_error']:.2%}"
                    + _p95_suffix(validation.get("p95_hybrid_error"))
                )
                lines.append(
                    f"Raw: MeanRE {validation['raw_mean_relative_error']:.2%}"
                    + _p95_suffix(validation.get("raw_p95_hybrid_error"))
                )
            else:
                lines.append(
                    f"验证: {method}，"
                    f"MeanRE {validation['mean_relative_error']:.2%}"
                )
        return lines


def build_metadata(
    *,
    model_type: str,
    damage_level: str,
    train_records: list[DamageRecord],
    config: Config,
    validation_mode: str,
    accuracy_report,
    train_time_seconds: float,
    pod_n_components: int | None = None,
) -> ModelMetadata:
    """训练完成后构建模型元数据。"""
    parameters: dict[str, Any] = {
        "validation_mode": validation_mode,
        "rbf_kernel": config.rbf_kernel,
        "rbf_smoothing": config.rbf_smoothing,
        "align_patterns": config.align_patterns,
        "denoise_sigma_spatial": config.denoise_sigma_spatial,
        "denoise_radius": config.denoise_radius,
        "eval_smoothing_sigma": config.eval_smoothing_sigma,
        "target_shape": list(config.target_shape),
    }
    if getattr(config, "rbf_epsilon", None) is not None:
        parameters["rbf_epsilon"] = float(config.rbf_epsilon)
    if model_type == "pod_rbf":
        parameters["pod_n_components"] = int(
            pod_n_components or config.pod_n_components
        )
    return ModelMetadata(
        model_id=uuid.uuid4().hex,
        created_at=_utc_now_iso(),
        app_version=__version__,
        schema_version=METADATA_SCHEMA_VERSION,
        model_format_version=MODEL_FORMAT_VERSION,
        model_type=model_type,
        damage_level=damage_level,
        training_samples=len(train_records),
        training_data_hash=training_data_hash(train_records),
        code_commit=git_commit_sha(),
        parameters=parameters,
        validation=_validation_summary(
            accuracy_report, config, validation_mode, train_time_seconds
        ),
    )


def sidecar_path(model_path: str | Path) -> Path:
    """模型元数据 sidecar 路径：<模型名>.joblib → <模型名>.meta.json。"""
    return Path(model_path).with_suffix(".meta.json")
