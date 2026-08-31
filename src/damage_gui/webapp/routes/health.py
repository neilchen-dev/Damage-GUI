from __future__ import annotations

from fastapi import APIRouter, Request

from damage_gui import __version__
from damage_gui.webapp.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse, name="health")
def health(request: Request) -> HealthResponse:
    context = request.app.state.web_context
    active_model_id = context.model_manager.active_model_id()
    return HealthResponse(
        version=__version__,
        model_ready=active_model_id is not None,
        active_model_id=active_model_id,
    )
