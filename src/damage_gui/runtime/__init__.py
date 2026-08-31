"""运行时路径解析（UI 无关）。

- app_base_dir()   应用根目录（源码为项目根，打包为 exe 所在目录）
- resource_path()  随包资源路径（兼容 PyInstaller _MEIPASS）

存储层（storage.db）、日志（logging_setup）等非 GUI 模块从这里导入，
不得依赖 damage_gui.gui 包——保持"算法/存储层零 GUI 依赖"的分层约束，
为 Web/无头运行时解耦。gui.resources 保留为向后兼容 shim。
"""
from damage_gui.runtime.paths import app_base_dir, resource_path

__all__ = ["app_base_dir", "resource_path"]
