"""GUI 资源与运行目录解析（源码 / PyInstaller 双模式）。"""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(filename: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).with_name(filename)


def app_base_dir() -> Path:
    """源码运行返回项目根目录，打包运行返回 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resolve_icon_paths() -> tuple[Path | None, Path | None]:
    ico_path = resource_path("damage_app_icon.ico")
    png_path = resource_path("damage_app_icon.png")
    return (
        ico_path if ico_path.exists() else None,
        png_path if png_path.exists() else None,
    )
