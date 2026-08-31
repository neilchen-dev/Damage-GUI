from __future__ import annotations

from fastapi import APIRouter, Request, Response

from damage_gui.webapp.dependencies import WebContext
from damage_gui.webapp.schemas import PredictionResponse
from damage_gui.webapp.serialization import prediction_response

router = APIRouter(prefix="/api/results", tags=["results"])


def _context(request: Request) -> WebContext:
    return request.app.state.web_context


def _item_and_descriptor(request: Request, run_id: str):
    context = _context(request)
    item = context.result_store.get(run_id)
    descriptor = (
        context.model_manager.get_descriptor(item.model_id)
        if item.response is None
        else None
    )
    return item, descriptor


@router.get("/{run_id}", response_model=PredictionResponse, name="get_result")
def get_result(run_id: str, request: Request) -> PredictionResponse:
    item, descriptor = _item_and_descriptor(request, run_id)
    if item.response is not None:
        return PredictionResponse.model_validate(item.response)
    return prediction_response(item, descriptor)


@router.get("/{run_id}/png", name="get_result_png")
def get_result_png(run_id: str, request: Request) -> Response:
    item, _descriptor = _item_and_descriptor(request, run_id)
    return Response(
        content=_context(request).result_store.ensure_png(item),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{run_id}.png"'},
    )


@router.get("/{run_id}/csv", name="get_result_csv")
def get_result_csv(run_id: str, request: Request) -> Response:
    item, _descriptor = _item_and_descriptor(request, run_id)
    return Response(
        content=_context(request).result_store.csv_bytes(item),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
    )
