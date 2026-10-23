"""主桌面入口（自 2.2 起指向 Qt 工作台，2026-10 起 Tk 桌面退役）。

历史：

- 2.2 之前 ``damage-gui`` 入口启动的是 Tk 桌面（:mod:`damage_gui.gui`）。
  2.2 完成 Qt 工作台重构后，主入口改为 Qt；Tk 桌面曾通过显式脚本
  ``damage-gui-tk``（:func:`damage_gui.gui.main_window.main`）继续提供。
- 2026-10 退役 Tk 桌面：``damage_gui.gui`` 子树整体删除（2847 行 Tk 代码）、
  ``damage-gui-tk`` 入口移除，桌面包从此**只有 Qt 一份**。
  :mod:`damage_gui.app` 仍保留历史科学符号以兼容旧 joblib/pickle 引用；
  桌面进程从本入口进入，避开兼容层在 GUI 启动期拉起 numpy/scipy/matplotlib。

本模块是 ``python -m damage_gui.desktop`` 与 ``damage-gui`` 控制台脚本的
目标，向后兼容旧 import 路径（``damage_gui.desktop`` 一直指向"桌面工作台"）。
"""
from __future__ import annotations


def main() -> None:
    """启动主桌面工作台（Qt 唯一实现）。"""
    from damage_gui.qt.app import main as run_qt

    run_qt()


if __name__ == "__main__":
    main()
