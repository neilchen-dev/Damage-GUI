"""Single source of truth for operator-controlled web runtime settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from damage_gui.runtime.paths import app_base_dir

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 3650


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def parse_port(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_PORT
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError("DAMAGE_GUI_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("DAMAGE_GUI_PORT must be between 1 and 65535")
    return port


def parse_retention_days(value: str | None) -> int:
    if value is None or not value.strip():
        return DEFAULT_RETENTION_DAYS
    try:
        days = int(value)
    except ValueError as exc:
        raise ValueError("DAMAGE_GUI_RESULT_RETENTION_DAYS must be an integer") from exc
    if not 1 <= days <= MAX_RETENTION_DAYS:
        raise ValueError(
            f"DAMAGE_GUI_RESULT_RETENTION_DAYS must be between 1 and {MAX_RETENTION_DAYS}"
        )
    return days


@dataclass(frozen=True)
class WebRuntimeSettings:
    """Resolved paths and network settings for one web process."""

    home: Path
    db_path: Path
    model_dir: Path
    result_dir: Path
    data_dir: Path | None
    retention_days: int
    host: str
    port: int
    default_model_id: str | None

    @classmethod
    def from_env(cls) -> WebRuntimeSettings:
        home = Path(_env_first("DAMAGE_GUI_HOME") or app_base_dir()).expanduser().resolve()
        db_path = Path(
            _env_first("DAMAGE_GUI_DB") or home / "db" / "damage_gui.db"
        ).expanduser().resolve()
        model_dir = Path(
            _env_first("DAMAGE_GUI_MODEL_DIR") or home / "models"
        ).expanduser().resolve()
        result_dir = Path(
            _env_first("DAMAGE_GUI_RESULT_DIR", "DAMAGE_GUI_WEB_RESULT_DIR")
            or home / "results"
        ).expanduser().resolve()
        data_value = _env_first("DAMAGE_GUI_DATA_DIR")
        data_dir = Path(data_value).expanduser().resolve() if data_value else None
        return cls(
            home=home,
            db_path=db_path,
            model_dir=model_dir,
            result_dir=result_dir,
            data_dir=data_dir,
            retention_days=parse_retention_days(
                os.environ.get("DAMAGE_GUI_RESULT_RETENTION_DAYS")
            ),
            host=_env_first("DAMAGE_GUI_HOST", "DAMAGE_GUI_WEB_HOST") or DEFAULT_HOST,
            port=parse_port(_env_first("DAMAGE_GUI_PORT", "DAMAGE_GUI_WEB_PORT")),
            default_model_id=_env_first("DAMAGE_GUI_DEFAULT_MODEL"),
        )
