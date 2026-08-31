from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Request

from damage_gui.storage.repositories import JobRepository, ModelRepository
from damage_gui.webapp.dependencies import WebContext
from damage_gui.webapp.schemas import AimRequest, AimResponse

router = APIRouter(prefix="/api", tags=["aim"])


def _context(request: Request) -> WebContext:
    return request.app.state.web_context


@router.post("/aim", response_model=AimResponse, name="aim")
def aim(payload: AimRequest, request: Request) -> AimResponse:
    context = _context(request)
    item = context.result_store.get(payload.run_id)
    started = time.perf_counter()

    from damage_gui.data.preprocessing import coordinate_axes
    from damage_gui.services.aim_service import AimService

    x_axis, y_axis = coordinate_axes(item.result.prediction.shape, item.config)
    result = AimService().optimize(
        item.result.prediction,
        x_axis,
        y_axis,
        spread_mode=payload.spread_mode,
        cep=payload.cep,
        rep=payload.rep,
        dep=payload.dep,
        rho=payload.rho,
        theta_deg=payload.theta_deg,
        reliability=payload.reliability,
        kernel_method=payload.kernel_method,
    )
    optimization = result.optimization
    job_id = uuid.uuid4().hex
    response = AimResponse(
        job_id=job_id,
        run_id=item.run_id,
        spread_mode=result.spread_mode,
        reliability=float(optimization.reliability),
        best_x=float(optimization.best_x),
        best_y=float(optimization.best_y),
        vmax=float(optimization.vmax),
        gain_relative=float(optimization.gain_relative),
        shift_distance=float(optimization.shift_distance),
        sigma_x=float(optimization.sigma_x),
        sigma_y=float(optimization.sigma_y),
        rho=float(optimization.rho),
        value_field_shape=tuple(int(value) for value in optimization.value_field.shape),
    )
    metadata = getattr(item.result, "model_metadata", None)
    database_model_id = None
    if metadata is not None and ModelRepository(context.db_path).upsert_model(metadata):
        database_model_id = metadata.model_id
    details = {
        "web_job": True,
        "result_kind": "aim",
        "summary": response.model_dump(mode="json"),
    }
    JobRepository(context.db_path).insert_job(
        job_id=job_id,
        kind="aim",
        status="SUCCESS",
        model_id=database_model_id,
        duration_ms=int((time.perf_counter() - started) * 1000),
        details=details,
    )
    return response
