from __future__ import annotations

import json
import string
import uuid
from pathlib import Path

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse

from damage_gui.errors import DataValidationError
from damage_gui.webapp.errors import (
    JobNotCancellableError,
    JobNotReadyError,
    ResultNotFoundError,
)
from damage_gui.webapp.jobs import WebJobManager, public_job
from damage_gui.webapp.schemas import BatchSubmitResponse, JobResponse

router = APIRouter(prefix="/api", tags=["jobs"])
MAX_BATCH_BYTES = 64 * 1024
MAX_BATCH_ROWS = 1_000
_SAFE_FILENAME_CHARS = frozenset(string.ascii_letters + string.digits + " ._-()[]")


def _manager(request: Request) -> WebJobManager:
    return request.app.state.web_jobs


def _context(request: Request):
    return request.app.state.web_context


def _display_filename(raw: str | None) -> str:
    name = (raw or "upload.csv").strip()
    if (
        not name
        or len(name) > 128
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(char not in _SAFE_FILENAME_CHARS for char in name)
        or not name.lower().endswith(".csv")
    ):
        raise DataValidationError("CSV 文件名无效")
    return name


def _job_details(row: dict) -> dict:
    try:
        value = json.loads(row.get("details_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _ensure_terminal(row: dict) -> None:
    if row.get("status") not in {"SUCCESS", "FAILED", "CANCELLED"}:
        raise JobNotReadyError()


@router.post("/batch", response_model=BatchSubmitResponse, name="submit_batch")
async def submit_batch(
    request: Request,
    model_id: str | None = Query(default=None),
) -> BatchSubmitResponse:
    """Accept a raw CSV body and enqueue it; the client supplies only a filename."""
    filename = _display_filename(request.headers.get("x-filename"))
    content = await request.body()
    if not content:
        raise DataValidationError("CSV 文件不能为空")
    if len(content) > MAX_BATCH_BYTES:
        raise DataValidationError("CSV 文件超过大小限制")
    context = _context(request)
    selected_model_id = model_id or context.model_manager.active_model_id()
    if selected_model_id is None:
        # Let the existing model-manager error semantics produce the public 503.
        context.model_manager.get_bundle(None)
    descriptor = context.model_manager.get_descriptor(selected_model_id)
    default_level = str((descriptor.metadata or {}).get("damage_level") or "F")

    upload_dir = (context.result_dir or (Path.cwd() / "web-results")) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{uuid.uuid4().hex}.csv"
    try:
        upload_path.write_bytes(content)
        from damage_gui.services.batch_service import BatchService

        parsed = BatchService().parse_csv(upload_path, default_level=default_level)
    finally:
        upload_path.unlink(missing_ok=True)
    if parsed.total > MAX_BATCH_ROWS:
        raise DataValidationError(f"CSV 行数超过限制（最多 {MAX_BATCH_ROWS} 行）")

    return BatchSubmitResponse.model_validate(
        _manager(request).submit(
            model_id=descriptor.model_id,
            parsed=parsed,
            input_source=filename,
        )
    )


@router.get("/jobs/{job_id}", response_model=JobResponse, name="get_job")
def get_job(job_id: str, request: Request) -> JobResponse:
    return JobResponse.model_validate(_manager(request).get(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse, name="cancel_job")
def cancel_job(job_id: str, request: Request) -> JobResponse:
    row = _manager(request).get_row(job_id)
    if row.get("kind") != "batch_prediction":
        raise JobNotCancellableError()
    return JobResponse.model_validate(_manager(request).cancel(job_id))


@router.get("/jobs/{job_id}/result/csv", name="get_job_result_csv")
def get_job_result_csv(job_id: str, request: Request):
    manager = _manager(request)
    row = manager.get_row(job_id)
    _ensure_terminal(row)
    if row.get("kind") == "prediction":
        item = _context(request).result_store.get(job_id)
        return Response(
            content=_context(request).result_store.csv_bytes(item),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.csv"'},
        )
    details = _job_details(row)
    if row.get("kind") != "batch_prediction" or not details.get("output_file"):
        raise ResultNotFoundError()
    path = manager.batch_output_path(job_id)
    if not path.is_file():
        raise ResultNotFoundError()
    return FileResponse(path, media_type="text/csv", filename=f"{job_id}.csv")


@router.get("/jobs/{job_id}/result", name="get_job_result")
def get_job_result(job_id: str, request: Request):
    manager = _manager(request)
    row = manager.get_row(job_id)
    _ensure_terminal(row)
    if row.get("kind") == "prediction":
        item = _context(request).result_store.get(job_id)
        if item.response is not None:
            return item.response
        from damage_gui.webapp.serialization import prediction_response

        descriptor = _context(request).model_manager.get_descriptor(item.model_id)
        return prediction_response(item, descriptor)

    details = _job_details(row)
    payload = {
        "job_id": str(row["id"]),
        "type": str(row.get("kind")),
        "state": public_job(row)["state"],
        "summary": details.get("summary") or {},
        "error_summary": row.get("error_summary"),
        "links": public_job(row)["links"],
    }
    if row.get("kind") not in {"aim", "batch_prediction"}:
        raise ResultNotFoundError()
    return payload
