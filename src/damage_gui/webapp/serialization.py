"""Conversion from domain result objects to explicit API response models."""
from __future__ import annotations

import math
from typing import Any

from damage_gui.webapp.dependencies import ModelDescriptor, StoredPrediction
from damage_gui.webapp.schemas import (
    AdviceResponse,
    ConditionResponse,
    ModelResponse,
    OODResponse,
    PredictionResponse,
    ResultLinks,
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def model_response(
    descriptor: ModelDescriptor,
    *,
    fallback_metadata: Any | None = None,
) -> ModelResponse:
    metadata = descriptor.metadata
    if metadata is None and fallback_metadata is not None:
        to_dict = getattr(fallback_metadata, "to_dict", None)
        metadata = to_dict() if callable(to_dict) else None
    return ModelResponse(
        model_id=descriptor.model_id,
        model_type=str(metadata["model_type"]) if metadata and "model_type" in metadata else None,
        damage_level=(
            str(metadata["damage_level"]) if metadata and "damage_level" in metadata else None
        ),
        created_at=str(metadata["created_at"]) if metadata and "created_at" in metadata else None,
        app_version=(
            str(metadata["app_version"])
            if metadata and "app_version" in metadata
            else None
        ),
        training_samples=(
            int(metadata["training_samples"])
            if metadata and "training_samples" in metadata
            else None
        ),
        metadata_available=metadata is not None,
        metadata=metadata,
    )


def prediction_response(item: StoredPrediction, descriptor: ModelDescriptor) -> PredictionResponse:
    result = item.result
    report = result.ood_report
    ood = None
    if report is not None:
        ood = OODResponse(
            level=str(report.level),
            level_label=str(report.level_label),
            distance=float(report.distance),
            is_extrapolation=bool(report.is_extrapolation),
            in_hull=report.in_hull,
            local_support=report.local_support,
        )

    metrics = None
    if result.truth_comparison_metrics:
        metrics = {
            str(key): number
            for key, value in result.truth_comparison_metrics.items()
            if (number := _number(value)) is not None
        }

    advice = result.advice
    return PredictionResponse(
        run_id=item.run_id,
        model=model_response(descriptor, fallback_metadata=result.model_metadata),
        condition=ConditionResponse(**result.condition.as_dict()),
        peak_intensity=float(result.peak_intensity),
        damage_area_ratio=float(result.damage_area_ratio),
        confidence=result.confidence,
        ood=ood,
        metrics=metrics or None,
        advice=AdviceResponse(
            has_truth=advice.has_truth,
            has_focus_damage=advice.has_focus_damage,
            scope=advice.scope,
            mean_relative_error=advice.mean_relative_error,
            p95_hybrid_error=advice.p95_hybrid_error,
            ood_geometry_reason=advice.ood_geometry_reason,
        ),
        elapsed_ms=int(result.elapsed_ms),
        links=ResultLinks(
            png=f"/api/results/{item.run_id}/png",
            csv=f"/api/results/{item.run_id}/csv",
        ),
    )
