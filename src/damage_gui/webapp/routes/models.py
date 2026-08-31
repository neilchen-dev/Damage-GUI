from __future__ import annotations

from fastapi import APIRouter, Request

from damage_gui.webapp.dependencies import ModelManager
from damage_gui.webapp.schemas import ModelResponse
from damage_gui.webapp.serialization import model_response

router = APIRouter(prefix="/api/models", tags=["models"])


def _manager(request: Request) -> ModelManager:
    return request.app.state.web_context.model_manager


@router.get("", response_model=list[ModelResponse], name="list_models")
def list_models(request: Request) -> list[ModelResponse]:
    return [model_response(item) for item in _manager(request).list_models()]


@router.get("/{model_id}", response_model=ModelResponse, name="get_model")
def get_model(model_id: str, request: Request) -> ModelResponse:
    return model_response(_manager(request).get_descriptor(model_id))
