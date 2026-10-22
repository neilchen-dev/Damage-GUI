"""应用图标解析：从 ``gui`` 主题层迁出的中立运行时能力。

``resolve_icon_paths`` 原本在 ``damage_gui.gui.resources`` 中实现，但
``qt.app`` 是图标解析的唯一消费方，把图标当作自然资源管理（运行时包
而非 GUI 包）能去掉"Qt 反向依赖 Tk GUI 包"这一历史耦合。

资源摆放于 ``damage_gui/runtime/assets/``，与代码同包；打包后由
``scripts/damagelab-qt.spec`` 的 datas 列表注入到 ``sys._MEIPASS``。
"""
from __future__ import annotations

import sys
from pathlib import Path

from damage_gui.runtime.paths import resource_path

__all__ = ["resolve_icon_paths"]


def _package_assets_dir() -> Path:
    """随包资源目录：源码运行取 runtime/，冻结运行取 _MEIPASS。"""
    return Path(__file__).parent / "assets"


def _candidates():
    """图标的候选解析位置（兼容历史命名）。

    当前只保留 ``damagelab-icon`` 一个固定基名；保留 ``damage_app_icon``
    与历史 ``.ico``/``.png`` 双后缀解析。
    """
    base = _package_assets_dir()
    return (
        base / "damagelab-icon",
        base / "damage_app_icon",
    )


def resolve_icon_paths() -> tuple[Path | None, Path | None]:
    """返回 ``(ico, png)`` 路径；任一不存在则该位为 ``None``。

    - 源码运行：从 ``runtime/assets/`` 解析
    - PyInstaller frozen：经 ``resource_path`` 走 ``sys._MEIPASS``
    """
    for stem in _candidates():
        stem_name = stem.name
        if getattr(sys, "frozen", False):
            ico = resource_path(f"damage_gui/runtime/assets/{stem_name}.ico")
            png = resource_path(f"damage_gui/runtime/assets/{stem_name}.png")
        else:
            ico = resource_path(f"{stem_name}.ico", base_dir=stem.parent)
            png = resource_path(f"{stem_name}.png", base_dir=stem.parent)
        if ico.exists() or png.exists():
            return (
                ico if ico.exists() else None,
                png if png.exists() else None,
            )
    return None, None
