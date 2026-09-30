"""运行时路径实现：源码 / PyInstaller 双模式解析。

从 damage_gui.gui.resources 迁移而来；GUI 包内保留 shim 以兼容历史导入
路径与打包 spec。app_base_dir() 是存储层与日志真正依赖的共享助手；
resource_path() 供随包资源解析（GUI 图标等），base_dir 显式传入以便
各调用方锚定自己的资源目录。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_path(filename: str, base_dir: Path | None = None) -> Path:
    """随包资源路径：打包运行取 sys._MEIPASS，源码运行取 base_dir。

    base_dir 缺省为本模块目录；GUI 图标等资源应显式传入资源所在目录，
    避免"实现迁移导致资源锚点漂移"。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return (base_dir if base_dir is not None else Path(__file__).parent) / filename


def _user_data_dir() -> Path:
    """平台用户数据目录（冻结运行时写数据库 / 日志 / 报告的位置）。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DamageLab"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "DamageLab"
        return Path.home() / "AppData" / "Local" / "DamageLab"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "DamageLab"
    return Path.home() / ".local" / "share" / "DamageLab"


def app_base_dir() -> Path:
    """应用数据根目录。

    源码运行返回项目根目录；打包（frozen）运行返回平台用户数据目录，
    而不是 exe 安装目录——安装目录可能只读（Program Files / /Applications），
    数据库与日志写入那里会在发布包上失败。DAMAGE_GUI_HOME 可显式覆盖
    （便携式部署 / 测试隔离均用它）。
    """
    configured_home = os.environ.get("DAMAGE_GUI_HOME")
    if configured_home:
        return Path(configured_home).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return _user_data_dir()
    return Path(__file__).resolve().parents[3]
