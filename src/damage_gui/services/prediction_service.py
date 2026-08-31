"""Prediction use-case orchestration independent of Tkinter."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from damage_gui.config import Config
from damage_gui.data.loader import Condition, DamageDataManager, read_damage_matrix
from damage_gui.data.preprocessing import evaluation_fields
from damage_gui.evaluation.metrics import metric_row
from damage_gui.model.bundle import DamageModelService, ModelBundle
from damage_gui.model.ood import OODReport


@dataclass(frozen=True)
class AdviceDecision:
    """Non-presentational decisions used by a GUI/CLI adapter."""

    has_truth: bool
    has_focus_damage: bool
    scope: str
    mean_relative_error: float | None
    p95_hybrid_error: float | None
    ood_geometry_reason: str | None


@dataclass(frozen=True)
class PredictionResult:
    """Structured output of one prediction use case."""

    condition: Condition
    prediction: np.ndarray
    truth: np.ndarray | None
    core_metrics: dict[str, Any] | None
    truth_comparison_metrics: dict[str, Any] | None
    ood_report: OODReport | None
    confidence: str | None
    model_metadata: Any | None
    elapsed_seconds: float
    peak_intensity: float
    damage_area_ratio: float
    advice: AdviceDecision

    @property
    def elapsed_ms(self) -> int:
        return int(self.elapsed_seconds * 1000)

    @property
    def truth_metrics(self) -> dict[str, Any] | None:
        """Compatibility alias for the truth-comparison metric row."""
        return self.truth_comparison_metrics

    @property
    def metadata(self) -> Any | None:
        """Short alias for serializers and existing model metadata consumers."""
        return self.model_metadata


class PredictionService:
    """Run prediction, OOD, exact-truth lookup, and current-case metrics."""

    def __init__(
        self,
        data_manager: DamageDataManager | None = None,
        *,
        model_service: DamageModelService | None = None,
        config: Config | None = None,
    ) -> None:
        self.data_manager = data_manager
        self.model_service = model_service
        self.config = config

    def predict(
        self,
        bundle: ModelBundle,
        condition: Condition,
        *,
        data_manager: DamageDataManager | None = None,
        config: Config | None = None,
    ) -> PredictionResult:
        resolved_config = config or self.config or bundle.resolved_config()
        manager = data_manager if data_manager is not None else self.data_manager
        started = time.perf_counter()
        if self.model_service is not None:
            prediction = self.model_service.predict_matrix(bundle, condition)
        else:
            prediction = bundle.model.predict_matrix(condition)

        detector = getattr(bundle, "ood_detector", None)
        ood_report = (
            detector.report(condition)
            if detector is not None and detector.is_fitted
            else None
        )

        truth = None
        record = None
        if manager is not None:
            try:
                record = manager.find_record(bundle.level, condition)
            except Exception:
                # Preserve the desktop behavior: a lookup problem does not
                # prevent showing the prediction; matrix read failures still
                # surface through the outer adapter error handler.
                record = None
        if record is not None:
            truth = read_damage_matrix(record.path, resolved_config)

        truth_metrics: dict[str, Any] | None = None
        has_focus_damage = False
        mean_re = None
        p95_hybrid = None
        if truth is not None:
            eval_true, eval_pred = evaluation_fields(truth, prediction, resolved_config)
            focus_mask = eval_true.ravel() > resolved_config.relative_error_threshold
            has_focus_damage = bool(np.any(focus_mask))
            if has_focus_damage:
                truth_metrics = metric_row(
                    f"damage_gt_{resolved_config.relative_error_threshold:.2f}",
                    eval_true.ravel()[focus_mask],
                    eval_pred.ravel()[focus_mask],
                    resolved_config.relative_error_threshold,
                    resolved_config,
                )
                mean_re = float(truth_metrics["MeanRelativeError"])
                p95_hybrid = float(truth_metrics["P95HybridError"])

        geometry_reason = None
        if ood_report is not None and ood_report.is_extrapolation:
            geometry_reason = "训练数据覆盖边缘"
            if ood_report.in_hull is False:
                geometry_reason = "训练工况全局凸包之外"
            elif getattr(ood_report, "local_support", None) is False:
                geometry_reason = "全局凸包内的局部数据空洞"

        peak = float(prediction.max())
        threshold = resolved_config.eval_focus_thresholds[-1]
        area_ratio = float(np.mean(prediction > threshold))
        core_metrics = None
        if mean_re is not None:
            core_metrics = {
                "MeanRelativeError": mean_re,
                "P95HybridError": p95_hybrid,
            }
        elapsed = time.perf_counter() - started
        advice = AdviceDecision(
            has_truth=truth is not None,
            has_focus_damage=has_focus_damage,
            scope="当前工况" if truth is not None and has_focus_damage else "",
            mean_relative_error=mean_re,
            p95_hybrid_error=p95_hybrid,
            ood_geometry_reason=geometry_reason,
        )
        return PredictionResult(
            condition=condition,
            prediction=prediction,
            truth=truth,
            core_metrics=core_metrics,
            truth_comparison_metrics=truth_metrics,
            ood_report=ood_report,
            confidence=ood_report.level_label if ood_report is not None else None,
            model_metadata=getattr(bundle, "metadata", None),
            elapsed_seconds=elapsed,
            peak_intensity=peak,
            damage_area_ratio=area_ratio,
            advice=advice,
        )


def predict(
    bundle: ModelBundle,
    condition: Condition,
    *,
    data_manager: DamageDataManager | None = None,
    model_service: DamageModelService | None = None,
    config: Config | None = None,
) -> PredictionResult:
    """Functional convenience API for headless callers."""
    return PredictionService(
        data_manager=data_manager,
        model_service=model_service,
        config=config,
    ).predict(bundle, condition)
