"""Optional FastAPI adapter for headless/server-side use.

Importing this package never imports Tkinter or the desktop GUI.  The web
dependencies are optional so the desktop installation remains unchanged.
"""
from __future__ import annotations

from damage_gui.webapp.app import create_app

__all__ = ["create_app"]
