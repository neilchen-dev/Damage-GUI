"""Training orchestration outside the Tk presentation layer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from damage_gui.evaluation.metrics import extract_core_metrics
from damage_gui.model.bundle import DamageModelService, ModelBundle
from damage_gui.runtime.paths import app_base_dir
from damage_gui.storage.db import resolve_db_path
from damage_gui.storage.repositories import JobRepository


@dataclass(frozen=True)
class TrainingResult:
    """Completed training bundle and persisted artifacts/summary."""

    bundle: ModelBundle
    accuracy_report_path: Path
    condition_report_path: Path
    mean_relative_error: float | None
    p95_hybrid_error: float | None
    db_recorded: bool
    raw_mean_relative_error: float | None = None
    raw_p95_hybrid_error: float | None = None

    @property
    def core_metrics(self) -> dict[str, float | None]:
        return {
            "MeanRelativeError": self.mean_relative_error,
            "P95HybridError": self.p95_hybrid_error,
        }


class TrainingService:
    """Orchestrate the existing ``DamageModelService.train_bundle`` pipeline."""

    def __init__(
        self,
        model_service: DamageModelService,
        *,
        db_path: str | Path | None = None,
        report_dir: str | Path | None = None,
    ) -> None:
        self.model_service = model_service
        self.db_path = resolve_db_path(db_path)
        self.report_dir = Path(report_dir) if report_dir is not None else app_base_dir()

    def train(
        self,
        level: str,
        *,
        validation_mode: str | None = None,
        model_type: str | None = None,
        pod_n_components: int | None = None,
        progress=None,
        cancel_check=None,
    ) -> TrainingResult:
        bundle = self.model_service.train_bundle(
            level,
            validation_mode=validation_mode,
            model_type=model_type,
            pod_n_components=pod_n_components,
            progress=progress,
            cancel_check=cancel_check,
        )
        return self._prepare_result(bundle)

    def train_bundle(self, *args, **kwargs) -> TrainingResult:
        """Alias using the scientific core's historical method terminology."""
        return self.train(*args, **kwargs)

    def _prepare_result(self, bundle: ModelBundle) -> TrainingResult:
        accuracy_path = self.report_dir / f"gui_accuracy_report_{bundle.level}.csv"
        condition_path = self.report_dir / f"gui_condition_report_{bundle.level}.csv"
        bundle.accuracy_report.to_csv(accuracy_path, index=False, encoding="utf-8-sig")
        bundle.condition_report.to_csv(condition_path, index=False, encoding="utf-8-sig")

        mean_re, p95_hybrid = extract_core_metrics(
            bundle.accuracy_report, bundle.resolved_config()
        )
        raw_mean_re, raw_p95_hybrid = (
            extract_core_metrics(
                bundle.accuracy_report, bundle.resolved_config(), field="raw"
            )
            if "field" in bundle.accuracy_report.columns
            else (None, None)
        )
        db_recorded = self._record_training_to_db(
            bundle, mean_re, p95_hybrid, raw_mean_re, raw_p95_hybrid
        )
        return TrainingResult(
            bundle=bundle,
            accuracy_report_path=accuracy_path,
            condition_report_path=condition_path,
            mean_relative_error=mean_re,
            p95_hybrid_error=p95_hybrid,
            db_recorded=db_recorded,
            raw_mean_relative_error=raw_mean_re,
            raw_p95_hybrid_error=raw_p95_hybrid,
        )

    def _record_training_to_db(
        self,
        bundle: ModelBundle,
        mean_re: float | None,
        p95_hybrid: float | None,
        raw_mean_re: float | None = None,
        raw_p95_hybrid: float | None = None,
    ) -> bool:
        """Record training trace; preserve the GUI's best-effort semantics."""
        if bundle.metadata is None:
            return False
        details: dict = {
            "validation_mode": bundle.validation_mode,
            "primary_field": "smoothed",
            "train_time_seconds": round(bundle.train_time_seconds, 3),
        }
        if mean_re is not None:
            details["mean_relative_error"] = float(mean_re)
        if p95_hybrid is not None:
            details["p95_hybrid_error"] = float(p95_hybrid)
        if raw_mean_re is not None:
            details["raw_mean_relative_error"] = float(raw_mean_re)
        if raw_p95_hybrid is not None:
            details["raw_p95_hybrid_error"] = float(raw_p95_hybrid)
        job_id = JobRepository(self.db_path).record_training_run(
            bundle.metadata,
            input_source=bundle.data_dir,
            duration_ms=int(bundle.train_time_seconds * 1000),
            details=details,
        )
        return job_id is not None
