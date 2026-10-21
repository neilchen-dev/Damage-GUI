"""Resolve Qt desktop icons in source and PyInstaller builds."""
from __future__ import annotations

import sys
from pathlib import Path

from damage_gui.runtime.paths import resource_path


def resolve_icon_paths() -> tuple[Path | None, Path | None]:
    assets = Path(__file__).with_name("assets")
    stem = "damage_gui/qt/assets/damagelab-icon" if getattr(sys, "frozen", False) else "damagelab-icon"
    ico = resource_path(f"{stem}.ico", base_dir=assets)
    png = resource_path(f"{stem}.png", base_dir=assets)
    return (ico if ico.is_file() else None, png if png.is_file() else None)
