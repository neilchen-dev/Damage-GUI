"""Phase 0 冒烟测试：桌面 GUI 构建冒烟 + 无头导入验证（不入测试套件）。

用法（临时 venv）:
    python scripts/smoke_phase0.py
退出码 0 = 全部通过。
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def check_headless_imports() -> None:
    """验证基础设施模块可在无 Tk 环境导入（同 tests/test_headless_imports.py）。"""
    from importlib.abc import MetaPathFinder

    blocked = ("tkinter", "damage_gui.gui.main_window")

    class _Blocker(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if any(fullname == b or fullname.startswith(b + ".") for b in blocked):
                raise ImportError(f"headless guard: {fullname}")
            return None

    blocker = _Blocker()
    sys.meta_path.insert(0, blocker)
    try:
        import damage_gui.app  # noqa: F401
        import damage_gui.gui.resources  # noqa: F401
        import damage_gui.logging_setup  # noqa: F401
        import damage_gui.storage.db  # noqa: F401
        import damage_gui.visualization.plots  # noqa: F401
        assert "tkinter" not in sys.modules
        assert "damage_gui.gui.main_window" not in sys.modules
    finally:
        sys.meta_path.remove(blocker)
    print("[1/3] headless imports OK (storage / logging / plots / app)")


def check_gui_smoke() -> None:
    """构建 Tk 主窗口后立即销毁（验证桌面路径仍可用，不进 mainloop）。"""
    from damage_gui.gui.main_window import DamagePredictionGUI, create_root

    root = create_root()
    root.withdraw()
    DamagePredictionGUI(root)
    root.update_idletasks()
    root.update()
    root.destroy()
    print("[2/3] desktop GUI smoke OK (window built and destroyed)")


def check_cli() -> None:
    """CLI --help 冒烟。"""
    from damage_gui.cli import main as cli_main

    assert callable(cli_main)
    print("[3/3] CLI entry OK")


if __name__ == "__main__":
    check_headless_imports()
    check_gui_smoke()
    check_cli()
    print("PHASE0_SMOKE_OK")
