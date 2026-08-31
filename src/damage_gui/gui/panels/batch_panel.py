"""Batch prediction controls."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.widgets import bind_tooltip, compact_path


class BatchPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, csv_var: tk.StringVar,
                 on_browse: Callable[[], None], on_run: Callable[[], None],
                 on_cancel: Callable[[], None]) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Batch input", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(self, text="Input CSV (job_id,h,v,deg,level)", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        path_row = ttk.Frame(self, style="Inspector.TFrame")
        path_row.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        path_row.columnconfigure(0, weight=1)
        ttk.Entry(path_row, textvariable=csv_var, style="App.TEntry").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(path_row, text="Browse…", command=on_browse,
                   style="Secondary.TButton").grid(row=0, column=1, padx=(5, 0))
        self.info_var = tk.StringVar(value="No batch file selected yet.")
        self.info_label = ttk.Label(
            self, textvariable=self.info_var, style="Muted.TLabel",
            justify="left", wraplength=220,
        )
        self.info_label.grid(row=3, column=0, sticky="ew")
        self._full_info = ""
        bind_tooltip(self.info_label, lambda: self._full_info)
        self.run_button = ttk.Button(self, text="Run Batch", command=on_run,
                                     style="Primary.TButton")
        self.run_button.grid(row=4, column=0, sticky="ew", pady=(10, 5))
        self.run_button.bind("<Return>", lambda _event: self.run_button.invoke())
        self.cancel_button = ttk.Button(self, text="Cancel", command=on_cancel,
                                        style="Secondary.TButton", state="disabled")
        self.cancel_button.grid(row=5, column=0, sticky="ew")

    def set_info(self, text: str, *, full_text: str = "") -> None:
        self.info_var.set(text)
        self._full_info = full_text

    def set_selected_path(self, path: str) -> None:
        self.set_info(f"Selected: {compact_path(path)}", full_text=f"Selected: {path}")
