"""运行时路径与图标解析（UI 无关）。

- app_base_dir()    应用数据根目录（源码为项目根，打包为平台用户数据目录）
- resource_path()   随包资源路径（兼容 PyInstaller _MEIPASS）
- resolve_icon_paths() 应用图标解析（assets 位于 runtime/assets/）

存储层（storage.db）、日志（logging_setup）、桌面与 Web 入口等所有非业务
算法模块从这里导入，保持"算法/存储层零 GUI 依赖"的分层约束。
"""
from damage_gui.runtime.icons import resolve_icon_paths
from damage_gui.runtime.paths import app_base_dir, resource_path

__all__ = ["app_base_dir", "resource_path", "resolve_icon_paths"]
