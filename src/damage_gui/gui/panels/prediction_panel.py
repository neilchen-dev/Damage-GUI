"""Single-condition prediction controls."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.config import CONDITION_LIMITS


class PredictionPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, h_var: tk.StringVar, v_var: tk.StringVar,
                 deg_var: tk.StringVar, on_predict: Callable[[], None]) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="Single prediction", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        for row, (label, key, variable, unit) in enumerate(
            (("Height h", "h", h_var, "m"), ("Velocity v", "v", v_var, "m/s"),
             ("Angle θ", "deg", deg_var, "°")), start=1
        ):
            ttk.Label(self, text=label, style="FieldLabel.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 6)
            )
            lo, hi, step = CONDITION_LIMITS[key]
            input_widget = ttk.Spinbox(
                self, textvariable=variable, from_=lo, to=hi,
                increment=step, style="App.TSpinbox"
            )
            input_widget.grid(
                row=row, column=1, sticky="ew", pady=2
            )
            if key == "deg":
                input_widget.bind(
                    "<Return>", lambda _event: self.predict_button.invoke() or "break"
                )
            ttk.Label(self, text=unit, style="Unit.TLabel").grid(
                row=row, column=2, sticky="w", padx=(6, 0)
            )
        self.columnconfigure(2, minsize=28)
        self.predict_button = ttk.Button(self, text="Run Prediction", command=on_predict,
                                         style="Primary.TButton")
        self.predict_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        self.predict_button.bind("<Return>", lambda _event: self.predict_button.invoke())
        ttk.Label(self, text="Reliability", style="Section.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 3)
        )
        self.reliability_var = tk.StringVar(value="No prediction yet.")
        ttk.Label(self, textvariable=self.reliability_var, style="Muted.TLabel",
                  justify="left", wraplength=220).grid(row=6, column=0, columnspan=3, sticky="ew")

    def set_reliability(self, text: str) -> None:
        self.reliability_var.set(text)
