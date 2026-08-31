"""Validation configuration summary and result context."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ValidationPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, validation_var: tk.StringVar) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Validation configuration", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(self, text="Active mode", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(self, textvariable=validation_var, style="Value.TLabel").grid(
            row=2, column=0, sticky="w", pady=(2, 10)
        )
        ttk.Label(self, text="Validation result", style="Section.TLabel").grid(
            row=3, column=0, sticky="w", pady=(4, 4)
        )
        self.result_var = tk.StringVar(value="No validation results yet.")
        ttk.Label(self, textvariable=self.result_var, style="Muted.TLabel",
                  justify="left", wraplength=220).grid(row=4, column=0, sticky="ew")

    def set_result(self, text: str) -> None:
        self.result_var.set(text)
