"""Dedicated desktop entry point.

The historical :mod:`damage_gui.app` module intentionally keeps its scientific
compatibility re-exports for old joblib/pickle references and public imports.
The desktop process enters here so those compatibility imports are not part of
normal GUI startup.
"""
from __future__ import annotations


def main() -> None:
    """Launch the Tk workbench without importing ``damage_gui.app``."""
    from damage_gui.gui.main_window import main as run_desktop

    run_desktop()


if __name__ == "__main__":
    main()
