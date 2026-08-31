"""数据访问层：models / jobs / prediction_results 三个仓储。

设计约束（追溯降级策略）：
- SQLite 故障绝不中断计算主流程：训练、批量预测照常完成；
- 但每次故障必须以 ERROR 级别记录完整 traceback（含操作与库名），
  并通过返回值 None/False 让调用方感知，进而在 GUI/CLI 中提示
  "结果未写入追溯数据库"——不允许静默吞掉。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from damage_gui.storage.db import connect, ensure_schema

if TYPE_CHECKING:
    from damage_gui.model.metadata import ModelMetadata

logger = logging.getLogger("damage_gui.storage")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _fail(operation: str, db_path: Path, exc: Exception) -> None:
    """统一的故障记录入口：ERROR 级完整 traceback，绝不静默。"""
    logger.exception(
        "SQLite 追溯记录失败：%s（数据库 %s）：%s —— 计算结果不受影响，"
        "但本次运行未入库，详见 traceback",
        operation, db_path.name, exc,
    )


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class ModelRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def upsert_model(
        self, metadata: ModelMetadata, artifact_path: str | None = None
    ) -> bool:
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO models (
                        id, created_at, app_version, model_type, damage_level,
                        training_samples, training_data_hash, code_commit,
                        parameters_json, validation_json, artifact_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metadata.model_id, metadata.created_at, metadata.app_version,
                        metadata.model_type, metadata.damage_level,
                        metadata.training_samples, metadata.training_data_hash,
                        metadata.code_commit,
                        _dump(metadata.parameters), _dump(metadata.validation),
                        artifact_path,
                    ),
                )
                conn.commit()
            return True
        except sqlite3.Error as exc:
            _fail("写入 models 表", self.db_path, exc)
            return False

    def list_models(self) -> list[dict[str, Any]] | None:
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                rows = conn.execute(
                    "SELECT * FROM models ORDER BY created_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            _fail("查询 models 表", self.db_path, exc)
            return None


class JobRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def insert_job(
        self,
        *,
        kind: str,
        job_id: str | None = None,
        status: str = "SUCCESS",
        model_id: str | None = None,
        input_source: str | None = None,
        duration_ms: int | None = None,
        error_summary: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str | None:
        """插入一条任务记录，返回 job_id；失败记录日志并返回 None。"""
        job_id = job_id or uuid.uuid4().hex
        now = _now_iso()
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, kind, status, model_id, input_source, created_at,
                        started_at, finished_at, duration_ms, error_summary,
                        details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id, kind, status, model_id, input_source, now,
                        now if status != "PENDING" else None,
                        now if status in ("SUCCESS", "FAILED", "CANCELLED") else None,
                        duration_ms, error_summary,
                        _dump(details) if details is not None else None,
                    ),
                )
                conn.commit()
            return job_id
        except sqlite3.Error as exc:
            _fail(f"写入 jobs 表（kind={kind}, status={status}）", self.db_path, exc)
            return None

    def record_training_run(
        self,
        metadata: ModelMetadata,
        *,
        input_source: str | None,
        duration_ms: int,
        details: dict[str, Any] | None = None,
        artifact_path: str | None = None,
    ) -> str | None:
        """训练完成的组合记录：模型入库 + SUCCESS 任务记录。"""
        model_repo = ModelRepository(self.db_path)
        if not model_repo.upsert_model(metadata, artifact_path):
            return None
        return self.insert_job(
            kind="training",
            status="SUCCESS",
            model_id=metadata.model_id,
            input_source=input_source,
            duration_ms=duration_ms,
            details=details,
        )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                row = conn.execute(
                    "SELECT * FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
            return dict(row) if row is not None else None
        except sqlite3.Error as exc:
            _fail("查询 jobs 表", self.db_path, exc)
            return None

    def update_job_state(
        self,
        job_id: str,
        *,
        status: str,
        model_id: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int | None = None,
        error_summary: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> bool:
        """Update a server-owned job lifecycle row without changing its ID."""
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                assignments = ["status = ?"]
                values: list[Any] = [status]
                if model_id is not None:
                    assignments.append("model_id = ?")
                    values.append(model_id)
                if started_at is not None:
                    assignments.append("started_at = ?")
                    values.append(started_at)
                if finished_at is not None or status in ("SUCCESS", "FAILED", "CANCELLED"):
                    assignments.append("finished_at = ?")
                    values.append(finished_at or _now_iso())
                if duration_ms is not None:
                    assignments.append("duration_ms = ?")
                    values.append(duration_ms)
                if error_summary is not None or status in ("SUCCESS", "FAILED", "CANCELLED"):
                    assignments.append("error_summary = ?")
                    values.append(error_summary)
                if details is not None:
                    assignments.append("details_json = ?")
                    values.append(_dump(details))
                values.append(job_id)
                cursor = conn.execute(
                    f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
                    values,
                )
                conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as exc:
            _fail(f"更新 jobs 表（job={job_id}, status={status}）", self.db_path, exc)
            return False

    def recent_jobs(self, limit: int = 20) -> list[dict[str, Any]] | None:
        return self.list_jobs(limit=limit, offset=0)

    def list_jobs(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]] | None:
        """Read-only paginated job history using the existing schema."""
        limit = max(0, min(int(limit), 1000))
        offset = max(0, int(offset))
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            _fail("查询 jobs 表（分页历史）", self.db_path, exc)
            return None

    def count_jobs(self) -> int | None:
        """Return the number of existing traceability jobs without schema changes."""
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                row = conn.execute("SELECT COUNT(*) AS total FROM jobs").fetchone()
            return int(row["total"]) if row is not None else 0
        except sqlite3.Error as exc:
            _fail("统计 jobs 表", self.db_path, exc)
            return None


class PredictionResultRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def record_batch_results(
        self,
        *,
        job_id: str,
        rows: list[dict[str, Any]],
        output_path: str | None = None,
    ) -> bool:
        """批量预测结果入库（单事务）。rows 为输出 CSV 同结构的字典列表。"""
        now = _now_iso()
        try:
            with closing(connect(self.db_path)) as conn:
                ensure_schema(conn)
                conn.executemany(
                    """
                    INSERT INTO prediction_results (
                        job_id, row_job_id, level, h, v, deg, status,
                        ood_level, ood_distance, peak_intensity,
                        damage_area_ratio, mean_relative_error,
                        p95_hybrid_error, duration_ms, error_summary,
                        output_path, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            job_id, row.get("job_id"), row.get("level"),
                            row.get("h"), row.get("v"), row.get("deg"),
                            row.get("status", "FAILED"),
                            row.get("ood_level"), row.get("ood_distance"),
                            row.get("peak_intensity"), row.get("damage_area_ratio"),
                            row.get("mean_relative_error"),
                            row.get("p95_hybrid_error"), row.get("duration_ms"),
                            row.get("error_message"), output_path, now,
                        )
                        for row in rows
                    ],
                )
                conn.commit()
            return True
        except sqlite3.Error as exc:
            _fail(f"写入 prediction_results 表（job={job_id}）", self.db_path, exc)
            return False
