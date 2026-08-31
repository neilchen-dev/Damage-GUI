"""批量预测执行器：逐工况预测 + OOD 可信度 + 可选真值对照 + SQLite 追溯。

处理链：CSV → 输入校验 → 批量预测 → 记录模型版本 → 结果摘要 →
CSV 输出（+ SQLite 追溯，失败时显式降级，不阻断计算）。
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from damage_gui.batch.schema import (
    OUTPUT_COLUMNS,
    BatchRowInput,
    InvalidBatchRow,
)
from damage_gui.config import Config
from damage_gui.data.loader import Condition, DamageDataManager, read_damage_matrix
from damage_gui.data.preprocessing import evaluation_fields
from damage_gui.errors import OperationCancelled, PredictionError
from damage_gui.evaluation.metrics import metric_row
from damage_gui.model.bundle import ModelBundle
from damage_gui.services.export_service import export_rows_csv
from damage_gui.storage.db import resolve_db_path
from damage_gui.storage.repositories import (
    JobRepository,
    ModelRepository,
    PredictionResultRepository,
)

logger = logging.getLogger("damage_gui.batch")

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass
class BatchRowOutcome:
    """单条工况的预测结果（输入回显 + 摘要指标 + 状态）。"""

    job_id: str
    level: str
    h: float
    v: float
    deg: float
    status: str = "SUCCESS"  # SUCCESS | FAILED
    model_id: str | None = None
    model_version: str | None = None
    ood_level: str | None = None
    ood_distance: float | None = None
    peak_intensity: float | None = None
    damage_area_ratio: float | None = None
    mean_relative_error: float | None = None
    p95_hybrid_error: float | None = None
    duration_ms: int | None = None
    error_message: str | None = None

    def to_output_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "level": self.level,
            "h": self.h,
            "v": self.v,
            "deg": self.deg,
            "status": self.status,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "ood_level": self.ood_level,
            "ood_distance": (
                round(self.ood_distance, 6)
                if self.ood_distance is not None else None
            ),
            "peak_intensity": (
                round(self.peak_intensity, 6)
                if self.peak_intensity is not None else None
            ),
            "damage_area_ratio": (
                round(self.damage_area_ratio, 6)
                if self.damage_area_ratio is not None else None
            ),
            "mean_relative_error": (
                round(self.mean_relative_error, 6)
                if self.mean_relative_error is not None else None
            ),
            "p95_hybrid_error": (
                round(self.p95_hybrid_error, 6)
                if self.p95_hybrid_error is not None else None
            ),
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


@dataclass
class BatchReport:
    """批量任务汇总。db_recorded=False 表示追溯入库失败（已记录 ERROR 日志）。"""

    model_id: str | None
    model_version: str | None
    total: int
    success_count: int
    failed_count: int
    cancelled: bool
    duration_ms: int
    rows: list[BatchRowOutcome] = field(default_factory=list)
    output_path: str | None = None
    db_recorded: bool = False

    @property
    def job_recorded(self) -> bool:
        return self.db_recorded


def _failed_outcome(
    row: BatchRowInput | InvalidBatchRow, message: str,
    model_id: str | None = None, model_version: str | None = None,
) -> BatchRowOutcome:
    h = getattr(row, "h", None)
    v = getattr(row, "v", None)
    deg = getattr(row, "deg", None)
    return BatchRowOutcome(
        job_id=row.job_id, level=getattr(row, "level", "F"),
        h=float(h) if h is not None else float("nan"),
        v=float(v) if v is not None else float("nan"),
        deg=float(deg) if deg is not None else float("nan"),
        status="FAILED", model_id=model_id, model_version=model_version,
        error_message=message,
    )


def _row_summaries(
    prediction: np.ndarray, config: Config
) -> tuple[float, float]:
    """峰值强度与毁伤面积占比（阈值取最严格毁伤区阈值）。"""
    peak = float(prediction.max())
    threshold = config.eval_focus_thresholds[-1]
    area_ratio = float(np.mean(prediction > threshold))
    return peak, area_ratio


def _truth_metrics(
    data_manager: DamageDataManager,
    bundle: ModelBundle,
    condition: Condition,
    prediction: np.ndarray,
    config: Config,
) -> tuple[float, float] | None:
    """命中精确工况真值时计算核心指标（MeanRE / P95 Hybrid）。"""
    try:
        record = data_manager.find_record(bundle.level, condition)
        if record is None:
            return None
        truth = read_damage_matrix(record.path, config)
    except (OSError, ValueError):
        return None
    eval_true, eval_pred = evaluation_fields(truth, prediction, config)
    mask = eval_true.ravel() > config.relative_error_threshold
    if not np.any(mask):
        return None
    metrics = metric_row(
        f"damage_gt_{config.relative_error_threshold:.2f}",
        eval_true.ravel()[mask], eval_pred.ravel()[mask],
        config.relative_error_threshold, config,
    )
    return float(metrics["MeanRelativeError"]), float(metrics["P95HybridError"])


def run_batch(
    bundle: ModelBundle,
    rows: list[BatchRowInput],
    *,
    invalid_rows: list[InvalidBatchRow] | None = None,
    data_manager: DamageDataManager | None = None,
    config: Config | None = None,
    output_path: str | Path | None = None,
    db_path: str | Path | None = None,
    input_source: str | None = None,
    job_id: str | None = None,
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> BatchReport:
    """执行批量预测。

    - 单行失败记录错误并继续下一行，不中断批次；
    - cancel_check 返回 True 时停止处理剩余行（cancelled=True）；
    - 结束后写输出 CSV（utf-8-sig）并尝试写入 SQLite 追溯数据库，
      入库失败不影响结果返回（db_recorded=False + ERROR 日志）。
    """
    invalid_rows = invalid_rows or []
    config = config or bundle.resolved_config()
    metadata = getattr(bundle, "metadata", None)
    model_id = metadata.model_id if metadata is not None else None
    model_version = metadata.app_version if metadata is not None else None

    outcomes: list[BatchRowOutcome] = []
    for invalid in invalid_rows:
        outcomes.append(
            _failed_outcome(
                invalid, f"第 {invalid.line_no} 行输入校验失败: {invalid.error}",
                model_id, model_version,
            )
        )

    total = len(rows) + len(invalid_rows)
    started = time.perf_counter()
    cancelled = False
    processed = 0
    for row in rows:
        if cancel_check is not None and cancel_check():
            cancelled = True
            break
        processed += 1
        if progress is not None:
            progress(
                len(outcomes), total,
                f"批量预测 {row.job_id}: h={row.h:g}, v={row.v:g}, deg={row.deg:g}",
            )
        row_started = time.perf_counter()
        outcome = BatchRowOutcome(
            job_id=row.job_id, level=row.level, h=row.h, v=row.v, deg=row.deg,
            model_id=model_id, model_version=model_version,
        )
        try:
            if row.level != bundle.level:
                raise PredictionError(
                    f"输入 level={row.level} 与模型等级 {bundle.level} 不一致"
                )
            condition = Condition(h=row.h, v=row.v, deg=row.deg)
            prediction = bundle.model.predict_matrix(condition)
            outcome.peak_intensity, outcome.damage_area_ratio = _row_summaries(
                prediction, config
            )
            detector = getattr(bundle, "ood_detector", None)
            if detector is not None and detector.is_fitted:
                ood = detector.report(condition)
                outcome.ood_level = ood.level
                outcome.ood_distance = float(ood.distance)
            if data_manager is not None:
                metrics = _truth_metrics(
                    data_manager, bundle, condition, prediction, config
                )
                if metrics is not None:
                    outcome.mean_relative_error, outcome.p95_hybrid_error = metrics
            outcome.duration_ms = int((time.perf_counter() - row_started) * 1000)
        except OperationCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 —— 单行失败不阻断批次
            outcome.status = "FAILED"
            outcome.error_message = str(exc)[:300]
            outcome.duration_ms = int((time.perf_counter() - row_started) * 1000)
            logger.error(
                "批量预测行 %s 失败: %s", row.job_id, exc,
                exc_info=True,
            )
        outcomes.append(outcome)

    duration_ms = int((time.perf_counter() - started) * 1000)
    success_count = sum(1 for item in outcomes if item.status == "SUCCESS")
    failed_count = len(outcomes) - success_count
    report = BatchReport(
        model_id=model_id, model_version=model_version, total=total,
        success_count=success_count, failed_count=failed_count,
        cancelled=cancelled, duration_ms=duration_ms, rows=outcomes,
    )

    if output_path is not None:
        _write_output_csv(output_path, outcomes)
        report.output_path = str(Path(output_path).resolve())

    _record_to_db(
        report, metadata=metadata, db_path=resolve_db_path(db_path),
        input_source=input_source, job_id=job_id,
    )
    logger.info(
        "批量预测完成: %d/%d 成功, %d 失败, 耗时 %d ms%s",
        success_count, total, failed_count, duration_ms,
        "（用户取消，剩余行未处理）" if cancelled else "",
    )
    return report


def _write_output_csv(
    output_path: str | Path, outcomes: list[BatchRowOutcome]
) -> None:
    export_rows_csv(
        [item.to_output_dict() for item in outcomes],
        OUTPUT_COLUMNS,
        output_path,
    )


def _record_to_db(
    report: BatchReport,
    *,
    metadata,
    db_path: Path,
    input_source: str | None,
    job_id: str | None = None,
) -> None:
    """批量结果入库（模型 upsert + job + 逐行结果）；失败时 ERROR 日志 +
    db_recorded=False，不影响已产出的计算结果。"""
    if metadata is not None:
        # 先落模型表，保证 jobs.model_id 外键成立（模型与任务同一追溯链）
        if not ModelRepository(db_path).upsert_model(metadata):
            report.db_recorded = False
            return
    jobs = JobRepository(db_path)
    details = {
        "total": report.total,
        "success": report.success_count,
        "failed": report.failed_count,
        "cancelled": report.cancelled,
        "output_csv": Path(report.output_path).name if report.output_path else None,
    }
    final_status = "CANCELLED" if report.cancelled else "SUCCESS"
    if job_id is None:
        job_id = jobs.insert_job(
            kind="batch_prediction",
            status=final_status,
            model_id=report.model_id,
            input_source=input_source,
            duration_ms=report.duration_ms,
            details=details,
        )
        if job_id is None:
            report.db_recorded = False
            return
    else:
        # A web caller owns the lifecycle row and closes it only after the
        # output rows have been recorded.  Avoid exposing a terminal state
        # before the web job manager has written its final progress snapshot.
        pass
    results_repo = PredictionResultRepository(db_path)
    report.db_recorded = results_repo.record_batch_results(
        job_id=job_id,
        rows=[item.to_output_dict() for item in report.rows],
        output_path=report.output_path,
    )
