"""Explicit request and response contracts for the first web API."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    service: str = "damage-gui-web"
    version: str
    model_ready: bool
    active_model_id: str | None = None


class ModelResponse(StrictModel):
    model_id: str
    model_type: str | None = None
    damage_level: str | None = None
    created_at: str | None = None
    app_version: str | None = None
    training_samples: int | None = None
    metadata_available: bool = False
    metadata: dict[str, Any] | None = None


class ConditionResponse(StrictModel):
    h: float
    v: float
    deg: float


class PredictionRequest(StrictModel):
    h: float
    v: float
    deg: float
    model_id: str | None = Field(default=None, pattern=_ID_PATTERN)

    @field_validator("h", "v", "deg")
    @classmethod
    def finite_condition(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("condition values must be finite")
        return value


class OODResponse(StrictModel):
    level: str
    level_label: str
    distance: float
    is_extrapolation: bool
    in_hull: bool | None = None
    local_support: bool | None = None


class AdviceResponse(StrictModel):
    has_truth: bool
    has_focus_damage: bool
    scope: str
    mean_relative_error: float | None = None
    p95_hybrid_error: float | None = None
    ood_geometry_reason: str | None = None


class ResultLinks(StrictModel):
    png: str
    csv: str


class PredictionResponse(StrictModel):
    run_id: str
    model: ModelResponse
    condition: ConditionResponse
    peak_intensity: float
    damage_area_ratio: float
    confidence: str | None = None
    ood: OODResponse | None = None
    metrics: dict[str, float] | None = None
    advice: AdviceResponse
    elapsed_ms: int
    links: ResultLinks


class AimRequest(StrictModel):
    run_id: str = Field(pattern=_ID_PATTERN)
    spread_mode: Literal["CEP", "REP_DEP"] = "CEP"
    cep: float | None = None
    rep: float | None = None
    dep: float | None = None
    rho: float = 0.0
    theta_deg: float | None = None
    reliability: float = Field(default=1.0, gt=0.0, le=1.0)
    kernel_method: Literal["cell_integrated", "sampled"] = "cell_integrated"

    @field_validator("cep", "rep", "dep", "rho", "theta_deg")
    @classmethod
    def finite_spread_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("aim parameters must be finite")
        return value


class AimResponse(StrictModel):
    job_id: str | None = None
    run_id: str
    spread_mode: str
    reliability: float
    best_x: float
    best_y: float
    vmax: float
    gain_relative: float
    shift_distance: float
    sigma_x: float
    sigma_y: float
    rho: float
    value_field_shape: tuple[int, int]


class HistoryItem(StrictModel):
    id: str
    kind: str
    status: str
    model_id: str | None = None
    input_source: str | None = None
    created_at: str
    duration_ms: int | None = None
    error_summary: str | None = None


class HistoryResponse(StrictModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int


class JobLinks(StrictModel):
    result: str | None = None
    csv: str | None = None


class JobResponse(StrictModel):
    job_id: str
    type: str
    state: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    progress: int = Field(ge=0, le=100)
    completed: int = Field(ge=0)
    total: int = Field(ge=0)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_summary: str | None = None
    links: JobLinks
    stage: str = ""
    model_id: str | None = None


class BatchSubmitResponse(JobResponse):
    type: Literal["batch_prediction"] = "batch_prediction"


class ErrorResponse(StrictModel):
    detail: str
