"""GUI 资源与运行目录解析（向后兼容 shim）。

路径实现已迁移至 damage_gui.runtime.paths（存储层/日志等非 GUI 模块
改从 runtime 导入，解除"下层依赖 gui 包"的违规）；本模块保留旧导入
路径 damage_gui.gui.resources 以兼容历史脚本与打包配置。

注意：app_base_dir/resource_path 从 runtime re-export，行为与迁移前
一致；resource_path 缺省锚定 runtime 模块目录，GUI 资源（图标）须
显式传入 gui 目录以保持解析位置不变。
"""
from __future__ import annotations

from pathlib import Path

from damage_gui.runtime.paths import app_base_dir, resource_path  # noqa: F401


def resolve_icon_paths() -> tuple[Path | None, Path | None]:
    gui_dir = Path(__file__).parent
    ico_path = resource_path("damage_app_icon.ico", base_dir=gui_dir)
    png_path = resource_path("damage_app_icon.png", base_dir=gui_dir)
    return (
        ico_path if ico_path.exists() else None,
        png_path if png_path.exists() else None,
    )
