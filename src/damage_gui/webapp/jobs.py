"""Bounded, process-local web job execution for long-running batch requests."""
from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from damage_gui.storage.repositories import JobRepository
from damage_gui.webapp.errors import (
    InvalidIdentifierError,
    JobCapacityError,
    JobNotFoundError,
    ServiceUnavailableError,
)

logger = logging.getLogger("damage_gui.web")
_JOB_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
_TERMINAL_DB_STATES = {"SUCCESS", "FAILED", "CANCELLED"}
_STATE_MAP = {"SUCCESS": "SUCCEEDED", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _safe_job_id(job_id: str) -> str:
    import re

    if not isinstance(job_id, str) or re.fullmatch(_JOB_ID_RE, job_id) is None:
        raise InvalidIdentifierError("任务标识符格式无效")
    return job_id


def _details(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("details_json")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def public_job(row: dict[str, Any]) -> dict[str, Any]:
    """Convert an internal SQLite job row to a safe web response dictionary."""
    detail = _details(row)
    progress = detail.get("progress") if isinstance(detail.get("progress"), dict) else {}
    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    total = int(progress.get("total", summary.get("total", 0)) or 0)
    completed = int(progress.get("completed", summary.get("completed", 0)) or 0)
    db_state = str(row.get("status", "FAILED"))
    state = _STATE_MAP.get(db_state, db_state)
    job_id = str(row["id"])
    links = {
        "result": f"/api/jobs/{job_id}/result" if db_state in _TERMINAL_DB_STATES else None,
        "csv": (
            f"/api/jobs/{job_id}/result/csv"
            if db_state in _TERMINAL_DB_STATES and detail.get("output_file")
            else None
        ),
    }
    return {
        "job_id": job_id,
        "type": str(row.get("kind", "batch_prediction")),
        "state": state,
        "progress": int(round(completed / total * 100)) if total else 0,
        "completed": max(0, min(completed, total)) if total else max(0, completed),
        "total": total,
        "created_at": str(row.get("created_at", "")),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "error_summary": row.get("error_summary"),
        "links": links,
        "stage": str(progress.get("stage", "")),
        "model_id": row.get("model_id"),
    }


@dataclass
class _WebJob:
    job_id: str
    model_id: str
    parsed: Any
    input_source: str
    output_path: Path
    cancel_event: threading.Event
    future: Future | None = None


class WebJobManager:
    """One-server bounded executor with SQLite-backed lifecycle snapshots."""

    def __init__(self, context, *, max_workers: int = 1, max_jobs: int = 2) -> None:
        self.context = context
        self.max_jobs = max(1, int(max_jobs))
        self._accepting = True
        self._lock = threading.RLock()
        self._jobs: dict[str, _WebJob] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="damage-gui-web-batch",
        )
        self._cleanup_old_batch_artifacts()
        self._recover_orphaned_jobs()

    def submit(self, *, model_id: str, parsed: Any, input_source: str) -> dict[str, Any]:
        with self._lock:
            if not self._accepting:
                raise ServiceUnavailableError("服务正在关闭，暂不接受新任务")
            self._drop_finished_jobs()
            if len(self._jobs) >= self.max_jobs:
                raise JobCapacityError()
            job_id = uuid.uuid4().hex
            output_path = self.batch_output_path(job_id)
            detail = {
                "web_job": True,
                "result_kind": "batch",
                "selected_model_id": model_id,
                "output_file": output_path.name,
                "progress": {
                    "completed": 0,
                    "total": int(parsed.total),
                    "stage": "Queued",
                },
            }
            stored_id = JobRepository(self.context.db_path).insert_job(
                job_id=job_id,
                kind="batch_prediction",
                status="PENDING",
                input_source=input_source,
                details=detail,
            )
            if stored_id is None:
                raise ServiceUnavailableError("任务追溯记录当前不可用")
            job = _WebJob(
                job_id=job_id,
                model_id=model_id,
                parsed=parsed,
                input_source=input_source,
                output_path=output_path,
                cancel_event=threading.Event(),
            )
            self._jobs[job_id] = job
            try:
                job.future = self._executor.submit(self._run, job)
            except Exception as exc:
                self._jobs.pop(job_id, None)
                JobRepository(self.context.db_path).update_job_state(
                    job_id, status="FAILED", error_summary="任务无法启动"
                )
                raise ServiceUnavailableError("任务当前无法启动") from exc
            return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        job_id = _safe_job_id(job_id)
        row = JobRepository(self.context.db_path).get_job(job_id)
        if row is None:
            raise JobNotFoundError()
        return public_job(row)

    def get_row(self, job_id: str) -> dict[str, Any]:
        job_id = _safe_job_id(job_id)
        row = JobRepository(self.context.db_path).get_job(job_id)
        if row is None:
            raise JobNotFoundError()
        return row

    def cancel(self, job_id: str) -> dict[str, Any]:
        job_id = _safe_job_id(job_id)
        row = self.get_row(job_id)
        if str(row.get("status")) in _TERMINAL_DB_STATES:
            return public_job(row)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.cancel_event.set()
                if job.future is not None and job.future.cancel():
                    details = _details(row)
                    details.setdefault("progress", {})["stage"] = "Cancelled before start"
                    JobRepository(self.context.db_path).update_job_state(
                        job_id,
                        status="CANCELLED",
                        details=details,
                        error_summary="用户取消任务",
                    )
            else:
                JobRepository(self.context.db_path).update_job_state(
                    job_id, status="CANCELLED", error_summary="用户取消任务"
                )
        return self.get(job_id)

    def batch_output_path(self, job_id: str) -> Path:
        job_id = _safe_job_id(job_id)
        root = self.context.result_dir or (Path.cwd() / "web-results")
        path = root / "batches" / f"{job_id}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def shutdown(self) -> None:
        with self._lock:
            self._accepting = False
            for job in self._jobs.values():
                job.cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job: _WebJob) -> None:
        repository = JobRepository(self.context.db_path)
        started_at = _now_iso()
        details = self._read_details(job.job_id)
        try:
            _model_id, bundle, _descriptor = self.context.model_manager.get_bundle(job.model_id)
            metadata = getattr(bundle, "metadata", None)
            repository.update_job_state(
                job.job_id,
                status="RUNNING",
                model_id=metadata.model_id if metadata is not None else None,
                started_at=started_at,
                details=details,
            )

            from damage_gui.data.loader import DamageDataManager
            from damage_gui.services.batch_service import BatchService

            data_manager = None
            candidate_data_dir = self.context.data_dir or getattr(bundle, "data_dir", None)
            if candidate_data_dir is not None and Path(candidate_data_dir).exists():
                data_manager = DamageDataManager(candidate_data_dir)

            def progress(done: int, total: int, stage: str) -> None:
                details["progress"] = {
                    "completed": int(done),
                    "total": int(total),
                    "stage": str(stage),
                }
                repository.update_job_state(
                    job.job_id, status="RUNNING", details=details
                )

            report = BatchService(
                data_manager=data_manager,
                config=bundle.resolved_config(),
            ).run(
                bundle,
                job.parsed,
                output_path=job.output_path,
                db_path=self.context.db_path,
                input_source=job.input_source,
                job_id=job.job_id,
                progress=progress,
                cancel_check=job.cancel_event.is_set,
            )
            final_status = (
                "CANCELLED"
                if report.cancelled
                else "FAILED" if report.failed_count else "SUCCESS"
            )
            summary = {
                "total": report.total,
                "completed": len(report.rows),
                "success_count": report.success_count,
                "failed_count": report.failed_count,
                "cancelled": report.cancelled,
                "duration_ms": report.duration_ms,
                "row_error_count": sum(1 for row in report.rows if row.error_message),
            }
            details["summary"] = summary
            details["progress"] = {
                "completed": len(report.rows),
                "total": report.total,
                "stage": "Cancelled" if report.cancelled else "Complete",
            }
            repository.update_job_state(
                job.job_id,
                status=final_status,
                duration_ms=report.duration_ms,
                details=details,
            )
        except Exception:  # noqa: BLE001 - sanitize at the web boundary
            logger.exception("Web batch job %s failed", job.job_id)
            details["progress"] = details.get("progress", {})
            details["progress"]["stage"] = "Failed"
            repository.update_job_state(
                job.job_id,
                status="FAILED",
                details=details,
                error_summary="任务执行失败，请查看服务器日志",
            )
        finally:
            with self._lock:
                self._jobs.pop(job.job_id, None)

    def _read_details(self, job_id: str) -> dict[str, Any]:
        return _details(self.get_row(job_id))

    def _drop_finished_jobs(self) -> None:
        for job_id, job in list(self._jobs.items()):
            if job.future is not None and job.future.done():
                self._jobs.pop(job_id, None)

    def _recover_orphaned_jobs(self) -> None:
        rows = JobRepository(self.context.db_path).list_jobs(limit=1000, offset=0) or []
        repository = JobRepository(self.context.db_path)
        for row in rows:
            if row.get("status") not in ("PENDING", "RUNNING"):
                continue
            if not _details(row).get("web_job"):
                continue
            repository.update_job_state(
                str(row["id"]),
                status="FAILED",
                error_summary="服务重启前任务未完成",
            )

    def _cleanup_old_batch_artifacts(self) -> None:
        root = self.context.result_dir
        if root is None:
            return
        retention_days = max(1, int(getattr(self.context, "retention_days", 7)))
        cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
        for directory in (root / "batches", root / "uploads"):
            if not directory.is_dir():
                continue
            try:
                for child in directory.iterdir():
                    if child.stat().st_mtime < cutoff:
                        if child.is_dir():
                            shutil.rmtree(child, ignore_errors=True)
                        else:
                            child.unlink(missing_ok=True)
            except OSError:
                logger.warning("Unable to clean old web batch artifacts")
