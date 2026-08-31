"""Export actions available in the current desktop application."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class ExportPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, on_csv: Callable[[], None],
                 on_png: Callable[[], None]) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Export current result", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            self,
            text="Export the current prediction matrix or the selected scientific figure.",
            style="Muted.TLabel", justify="left", wraplength=220,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(self, text="Export CSV…", command=on_csv,
                   style="Secondary.TButton").grid(row=2, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(self, text="Export PNG…", command=on_png,
                   style="Secondary.TButton").grid(row=3, column=0, sticky="ew")
