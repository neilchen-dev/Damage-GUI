"""Validation configuration summary and result context."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from damage_gui.gui.i18n import Translator


class ValidationPanel(ttk.Frame):
    def __init__(
        self, parent: tk.Misc, *, validation_var: tk.StringVar, translator: Translator | None = None
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.validation"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.active_label = ttk.Label(
            self, text=self.translator.t("panel.active_mode"), style="FieldLabel.TLabel"
        )
        self.active_label.grid(row=1, column=0, sticky="w")
        ttk.Label(self, textvariable=validation_var, style="Value.TLabel").grid(
            row=2, column=0, sticky="w", pady=(2, 10)
        )
        self.result_title = ttk.Label(
            self, text=self.translator.t("panel.validation_result"), style="Section.TLabel"
        )
        self.result_title.grid(row=3, column=0, sticky="w", pady=(4, 4))
        self.result_var = tk.StringVar(value=self.translator.t("panel.no_validation_result"))
        ttk.Label(
            self, textvariable=self.result_var, style="Muted.TLabel", justify="left", wraplength=220
        ).grid(row=4, column=0, sticky="ew")
        self.translator.subscribe(self.apply_language)

    def set_result(self, text: str) -> None:
        self.result_var.set(text)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.validation"))
        self.active_label.configure(text=self.translator.t("panel.active_mode"))
        self.result_title.configure(text=self.translator.t("panel.validation_result"))
        if self.result_var.get() in {"No validation results yet.", "暂无验证结果。"}:
            self.result_var.set(self.translator.t("panel.no_validation_result"))
