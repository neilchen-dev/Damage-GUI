"""Qt desktop entry point.

Usage::

    damage-gui-qt

or::

    pip install -e ".[desktop-qt]"
    python -m damage_gui.qt.app

Requires PySide6.  If the dependency is missing we print a friendly
error instead of dumping a raw ImportError traceback.

Release hardening (Phase 2.5):
- uncaught exceptions are logged (full traceback) instead of killing
  the window silently;
- application metadata (name / version / icon) is registered so the
  dock/taskbar entry and About dialog are correct in frozen builds;
- startup records version + platform to the rotating log.
"""
from __future__ import annotations

import sys


def _ensure_pyside6() -> None:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Error: PySide6 is not installed.\n"
            "Install it with:\n\n"
            "    pip install -e \".[desktop-qt]\"\n\n"
            "or:\n\n"
            "    pip install PySide6 matplotlib\n"
        )
        sys.exit(2)


def _install_excepthook() -> None:
    """兜底未捕获异常：完整 traceback 进日志，应用继续运行。

    UI event handler 中的普通异常不应让整个程序消失（Phase 2.5 §27）；
    Qt slot 内的异常在部分 PySide6 版本会直接终止进程，这里统一接管。
    """
    import logging

    logger = logging.getLogger("damage_gui")

    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.exception(
            "Uncaught exception: %s: %s", exc_type.__name__, exc_value,
            exc_info=(exc_type, exc_value, exc_tb),
        )

    sys.excepthook = hook


def _app_icon():
    """应用图标：随包资源，源码 / frozen 双模式。"""
    from PySide6.QtGui import QIcon

    from damage_gui.gui.resources import resolve_icon_paths

    _, png = resolve_icon_paths()
    if png is not None and png.is_file():
        return QIcon(str(png))
    return QIcon()


def main() -> None:
    _ensure_pyside6()
    from PySide6.QtWidgets import QApplication

    from damage_gui import __version__
    from damage_gui.logging_setup import setup_logging
    from damage_gui.qt.main_window import DamageQtMainWindow
    from damage_gui.qt.theme import build_stylesheet

    setup_logging()
    _install_excepthook()

    import logging
    import platform

    logging.getLogger("damage_gui").info(
        "DamageLab %s starting (Qt desktop, Python %s, %s)",
        __version__, platform.python_version(), platform.platform(),
    )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DamageLab")
    app.setApplicationDisplayName("DamageLab")
    app.setOrganizationName("DamageLab")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(_app_icon())
    app.setStyleSheet(build_stylesheet())

    window = DamageQtMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
