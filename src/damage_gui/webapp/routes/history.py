from __future__ import annotations

from fastapi import APIRouter, Query, Request

from damage_gui.storage.repositories import JobRepository
from damage_gui.webapp.errors import ServiceUnavailableError
from damage_gui.webapp.schemas import HistoryItem, HistoryResponse

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryResponse, name="history")
def history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> HistoryResponse:
    context = request.app.state.web_context
    repository = JobRepository(context.db_path)
    rows = repository.list_jobs(limit=limit, offset=offset)
    total = repository.count_jobs()
    if rows is None or total is None:
        raise ServiceUnavailableError("追溯数据库当前不可用")
    items = [
        HistoryItem(
            id=str(row["id"]),
            kind=str(row["kind"]),
            status=str(row["status"]),
            model_id=row.get("model_id"),
            input_source=row.get("input_source"),
            created_at=str(row["created_at"]),
            duration_ms=row.get("duration_ms"),
            error_summary=row.get("error_summary"),
        )
        for row in rows
    ]
    return HistoryResponse(items=items, total=total, limit=limit, offset=offset)
