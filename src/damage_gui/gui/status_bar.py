"""Thin functional task status bar."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from damage_gui.gui.i18n import Translator
from damage_gui.gui.theme import THEME


class StatusBar(ttk.Frame):
    """Status, task stage and progress without decorative animation."""

    def __init__(self, parent: tk.Misc, *, translator: Translator | None = None) -> None:
        super().__init__(parent, style="Status.TFrame", padding=(8, 2, 8, 2))
        self.translator = translator or Translator()
        self.columnconfigure(1, weight=1)
        self._status_message_key: str | None = "status.initial"
        self.status_var = tk.StringVar(value=self.translator.t("status.initial"))
        self.stage_var = tk.StringVar(value="")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.percent_var = tk.StringVar(value="0%")
        self.state_label = ttk.Label(
            self, text=self.translator.t("status.ready"), style="Status.TLabel"
        )
        self.state_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.status_message = ttk.Label(self, textvariable=self.status_var, style="Status.TLabel")
        self.status_message.grid(row=0, column=1, sticky="w")
        self.stage_label = ttk.Label(self, textvariable=self.stage_var, style="StatusValue.TLabel")
        self.stage_label.grid(row=0, column=2, sticky="e", padx=(10, 8))
        self.progress_bar = ttk.Progressbar(
            self,
            variable=self.progress_var,
            maximum=100.0,
            style="App.Horizontal.TProgressbar",
            length=96,
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
        self._status_kind = "info"
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        labels = {
            "info": "status.ready",
            "busy": "status.running",
            "ok": "status.complete",
            "error": "status.error",
        }
        self.state_label.configure(
            text=self.translator.t(labels.get(self._status_kind, "status.ready"))
        )
        if self._status_message_key is not None:
            self.status_var.set(self.translator.t(self._status_message_key))

    def set_status(self, text: str, kind: str = "info") -> None:
        self._status_kind = kind if kind in {"info", "busy", "ok", "error"} else "info"
        self._status_message_key = None
        self.status_var.set(text)
        labels = {
            "info": "status.ready",
            "busy": "status.running",
            "ok": "status.complete",
            "error": "status.error",
        }
        color = self._colors.get(kind, self._colors["info"])
        self.state_label.configure(
            text=self.translator.t(labels.get(kind, "status.ready")), foreground=color
        )

    def set_progress(self, percent: float, stage: str) -> None:
        self.progress_var.set(percent)
        self.percent_var.set(f"{percent:.0f}%")
        self.stage_var.set(stage)

    def reset_progress(self) -> None:
        self.set_progress(0.0, "")
