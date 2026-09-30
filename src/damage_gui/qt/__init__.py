"""Qt desktop front-end scaffolding (Phase 1).

This package deliberately reuses :mod:`damage_gui.services`,
:mod:`damage_gui.model`, :mod:`damage_gui.visualization` and the existing
:class:`damage_gui.gui.i18n.Translator`.  No business logic lives here.
"""
from __future__ import annotations


def is_qt_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False
    return True


__all__ = ["is_qt_available"]
