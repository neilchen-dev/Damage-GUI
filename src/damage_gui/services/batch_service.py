"""Shared batch input/execution orchestration for GUI and CLI adapters."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from damage_gui.batch.runner import BatchReport, run_batch
from damage_gui.batch.schema import ParsedBatch, parse_batch_csv
from damage_gui.config import Config
from damage_gui.data.loader import DamageDataManager
from damage_gui.model.bundle import ModelBundle


class BatchService:
    """Facade around the stable batch engine and CSV parser."""

    def __init__(
        self,
        data_manager: DamageDataManager | None = None,
        config: Config | None = None,
    ) -> None:
        self.data_manager = data_manager
        self.config = config

    def parse_csv(self, path: str | Path, *, default_level: str = "F") -> ParsedBatch:
        return parse_batch_csv(path, default_level=default_level)

    def run(
        self,
        bundle: ModelBundle,
        parsed: ParsedBatch,
        *,
        data_manager: DamageDataManager | None = None,
        output_path: str | Path | None = None,
        db_path: str | Path | None = None,
        input_source: str | None = None,
        job_id: str | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> BatchReport:
        """Run a parsed batch while preserving runner behavior and callbacks."""
        return run_batch(
            bundle,
            parsed.rows,
            invalid_rows=parsed.invalid,
            data_manager=data_manager if data_manager is not None else self.data_manager,
            config=self.config,
            output_path=output_path,
            db_path=db_path,
            input_source=input_source,
            job_id=job_id,
            progress=progress,
            cancel_check=cancel_check,
        )


def parse_batch_input(path: str | Path, *, default_level: str = "F") -> ParsedBatch:
    """Functional convenience API for non-GUI callers."""
    return BatchService().parse_csv(path, default_level=default_level)


def run_batch_service(
    bundle: ModelBundle,
    parsed: ParsedBatch,
    **kwargs,
) -> BatchReport:
    """Functional convenience API delegating to ``BatchService``."""
    return BatchService().run(bundle, parsed, **kwargs)
