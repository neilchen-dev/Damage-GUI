"""History context panel preserving the existing traceability scope."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from damage_gui.gui.widgets import bind_tooltip, compact_path


class HistoryPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, db_path: str) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="History", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            self,
            text=("Runs are recorded in the existing SQLite traceability database.\n"
                  "This desktop view is read-only and compact."),
            style="Muted.TLabel", justify="left", wraplength=220,
        ).grid(row=1, column=0, sticky="ew")
        ttk.Label(self, text="Database", style="FieldLabel.TLabel").grid(
            row=2, column=0, sticky="w", pady=(12, 3)
        )
        self.database_label = ttk.Label(
            self, text=compact_path(db_path), style="Value.TLabel", anchor="w"
        )
        self.database_label.grid(row=3, column=0, sticky="ew")
        bind_tooltip(self.database_label, db_path)
