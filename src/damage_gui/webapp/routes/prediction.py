from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request

from damage_gui.storage.repositories import JobRepository, ModelRepository
from damage_gui.webapp.dependencies import WebContext
from damage_gui.webapp.schemas import PredictionRequest, PredictionResponse
from damage_gui.webapp.serialization import prediction_response

router = APIRouter(prefix="/api", tags=["prediction"])
logger = logging.getLogger("damage_gui.web")


def _context(request: Request) -> WebContext:
    return request.app.state.web_context


@router.post("/predict", response_model=PredictionResponse, name="predict")
def predict(payload: PredictionRequest, request: Request) -> PredictionResponse:
    context = _context(request)
    model_id, bundle, descriptor = context.model_manager.get_bundle(payload.model_id)

    from damage_gui.data.loader import DamageDataManager
    from damage_gui.services.conditions import validate_condition
    from damage_gui.services.prediction_service import PredictionService

    condition = validate_condition(h=payload.h, v=payload.v, deg=payload.deg)
    data_manager = None
    configured_data_dir = context.data_dir
    candidate_data_dir = configured_data_dir
    if candidate_data_dir is None and getattr(bundle, "data_dir", None):
        candidate_data_dir = bundle.data_dir
    if candidate_data_dir is not None:
        candidate = Path(candidate_data_dir)
        if candidate.exists():
            data_manager = DamageDataManager(candidate)

    config = bundle.resolved_config()
    result = PredictionService(data_manager=data_manager).predict(
        bundle, condition, config=config
    )
    item = context.result_store.put(model_id=model_id, result=result, config=config)
    response = prediction_response(item, descriptor)
    response_data = response.model_dump(mode="json")
    try:
        item = context.result_store.persist(item, response_data)
    except Exception:  # noqa: BLE001 - disk retention must not break prediction
        logger.exception("Unable to persist web prediction result %s", item.run_id)

    metadata = getattr(result, "model_metadata", None)
    database_model_id = None
    if metadata is not None and ModelRepository(context.db_path).upsert_model(metadata):
        database_model_id = metadata.model_id
    details = {
        "web_job": True,
        "result_kind": "prediction",
        "summary": {
            "condition": response_data["condition"],
            "peak_intensity": response_data["peak_intensity"],
            "damage_area_ratio": response_data["damage_area_ratio"],
        },
    }
    if JobRepository(context.db_path).insert_job(
        job_id=item.run_id,
        kind="prediction",
        status="SUCCESS",
        model_id=database_model_id,
        duration_ms=response.elapsed_ms,
        details=details,
    ) is None:
        logger.error("Unable to record web prediction history for %s", item.run_id)
    return response
