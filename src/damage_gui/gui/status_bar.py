"""Thin functional task status bar."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from damage_gui.gui.theme import THEME


class StatusBar(ttk.Frame):
    """Status, task stage and progress without decorative animation."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Status.TFrame", padding=(8, 2, 8, 2))
        self.columnconfigure(1, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        self.stage_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.percent_var = tk.StringVar(value="0%")
        self.state_label = ttk.Label(self, text="Ready", style="Status.TLabel")
        self.state_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.status_message = ttk.Label(self, textvariable=self.status_var, style="Status.TLabel")
        self.status_message.grid(row=0, column=1, sticky="w")
        self.stage_label = ttk.Label(self, textvariable=self.stage_var, style="StatusValue.TLabel")
        self.stage_label.grid(row=0, column=2, sticky="e", padx=(10, 8))
        self.progress_bar = ttk.Progressbar(
            self, variable=self.progress_var, maximum=100.0,
            style="App.Horizontal.TProgressbar", length=96,
        )
        self.progress_bar.grid(row=0, column=3, sticky="e")
        ttk.Label(self, textvariable=self.percent_var, style="StatusValue.TLabel", width=4).grid(
            row=0, column=4, sticky="e", padx=(5, 0)
        )
        self._colors = {
            "info": THEME.text,
            "busy": THEME.busy,
            "ok": THEME.success,
            "error": THEME.danger,
        }

    def set_status(self, text: str, kind: str = "info") -> None:
        self.status_var.set(text)
        labels = {"info": "Ready", "busy": "Running", "ok": "Complete", "error": "Error"}
        color = self._colors.get(kind, self._colors["info"])
        self.state_label.configure(text=labels.get(kind, "Ready"), foreground=color)

    def set_progress(self, percent: float, stage: str) -> None:
        self.progress_var.set(percent)
        self.percent_var.set(f"{percent:.0f}%")
        self.stage_var.set(stage)

    def reset_progress(self) -> None:
        self.set_progress(0.0, "")
