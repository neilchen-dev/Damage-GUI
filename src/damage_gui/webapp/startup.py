"""Validate and prepare a production web runtime before ASGI startup."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from damage_gui.storage.db import init_database
from damage_gui.webapp.dependencies import ModelManager
from damage_gui.webapp.settings import WebRuntimeSettings

logger = logging.getLogger("damage_gui.web.startup")


def _ensure_directory(path: Path, label: str) -> None:
    try:
        if path.exists() and not path.is_dir():
            raise RuntimeError(f"{label} is not a directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Cannot create {label}: {path} ({exc})") from exc


def _check_writable(directory: Path, label: str) -> None:
    probe = directory / f".damagelab-write-test-{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="ascii")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        probe.unlink(missing_ok=True)
        raise RuntimeError(f"{label} is not writable: {directory} ({exc})") from exc


def _check_readable(directory: Path, label: str) -> None:
    try:
        next(directory.iterdir(), None)
    except OSError as exc:
        raise RuntimeError(f"{label} is not readable: {directory} ({exc})") from exc


def validate_startup(settings: WebRuntimeSettings | None = None) -> WebRuntimeSettings:
    """Validate paths, initialize SQLite, and validate an explicit default model.

    Model artifacts are intentionally not loaded here.  Metadata discovery is
    enough to catch a bad configured model ID without adding model load cost to
    process startup.
    """
    settings = settings or WebRuntimeSettings.from_env()
    _ensure_directory(settings.home, "DAMAGE_GUI_HOME")
    _ensure_directory(settings.db_path.parent, "database directory")
    _ensure_directory(settings.model_dir, "model directory")
    _ensure_directory(settings.result_dir, "result directory")
    if settings.data_dir is not None:
        _ensure_directory(settings.data_dir, "data directory")

    _check_writable(settings.db_path.parent, "database directory")
    _check_readable(settings.model_dir, "model directory")
    _check_writable(settings.result_dir, "result directory")
    if not init_database(settings.db_path):
        raise RuntimeError(f"Cannot initialize SQLite database: {settings.db_path}")
    if settings.default_model_id:
        manager = ModelManager(
            settings.model_dir, default_model_id=settings.default_model_id
        )
        model_ids = {item.model_id for item in manager.list_models()}
        if settings.default_model_id not in model_ids:
            raise RuntimeError(
                "DAMAGE_GUI_DEFAULT_MODEL was not found in "
                f"{settings.model_dir}: {settings.default_model_id}"
            )

    logger.info(
        "Web runtime validated: db=%s models=%s results=%s retention_days=%d",
        settings.db_path,
        settings.model_dir,
        settings.result_dir,
        settings.retention_days,
    )
    return settings


def main() -> None:
    """Container entrypoint validation command."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        validate_startup()
    except (RuntimeError, ValueError) as exc:
        logger.error("Web runtime validation failed: %s", exc)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
