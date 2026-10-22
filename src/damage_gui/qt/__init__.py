"""Qt desktop workbench — the sole desktop front-end since the Tk retirement.

This package deliberately reuses :mod:`damage_gui.services`,
:mod:`damage_gui.model`, :mod:`damage_gui.visualization` and the shared
:class:`damage_gui.i18n.Translator` (a UI-framework-neutral layer; the Qt
package no longer depends on the legacy Tk implementation).  No business
logic lives here.
"""
from __future__ import annotations


def is_qt_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False
    return True


__all__ = ["is_qt_available"]
