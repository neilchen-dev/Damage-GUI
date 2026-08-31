"""Single-condition prediction controls."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.config import CONDITION_LIMITS
from damage_gui.gui.i18n import Translator


class PredictionPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        h_var: tk.StringVar,
        v_var: tk.StringVar,
        deg_var: tk.StringVar,
        on_predict: Callable[[], None],
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.prediction"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.field_labels: dict[str, ttk.Label] = {}
        for row, (label, key, variable, unit) in enumerate(
            (
                ("panel.height", "h", h_var, "m"),
                ("panel.velocity", "v", v_var, "m/s"),
                ("panel.angle", "deg", deg_var, "°"),
            ),
            start=1,
        ):
            field_label = ttk.Label(self, text=self.translator.t(label), style="FieldLabel.TLabel")
            field_label.grid(row=row, column=0, sticky="w", padx=(0, 6))
            self.field_labels[label] = field_label
            lo, hi, step = CONDITION_LIMITS[key]
            input_widget = ttk.Spinbox(
                self, textvariable=variable, from_=lo, to=hi, increment=step, style="App.TSpinbox"
            )
            input_widget.grid(row=row, column=1, sticky="ew", pady=2)
            if key == "deg":
                input_widget.bind(
                    "<Return>", lambda _event: self.predict_button.invoke() or "break"
                )
            ttk.Label(self, text=unit, style="Unit.TLabel").grid(
                row=row, column=2, sticky="w", padx=(6, 0)
            )
        self.columnconfigure(2, minsize=28)
        self.predict_button = ttk.Button(
            self,
            text=self.translator.t("panel.run_prediction"),
            command=on_predict,
            style="Primary.TButton",
        )
        self.predict_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        self.predict_button.bind("<Return>", lambda _event: self.predict_button.invoke())
        self.reliability_title = ttk.Label(
            self, text=self.translator.t("panel.reliability"), style="Section.TLabel"
        )
        self.reliability_title.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 3))
        self.reliability_var = tk.StringVar(value=self.translator.t("status.no_prediction"))
        ttk.Label(
            self,
            textvariable=self.reliability_var,
            style="Muted.TLabel",
            justify="left",
            wraplength=220,
        ).grid(row=6, column=0, columnspan=3, sticky="ew")
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.prediction"))
        for text_key, label in self.field_labels.items():
            label.configure(text=self.translator.t(text_key))
        self.predict_button.configure(text=self.translator.t("panel.run_prediction"))
        self.reliability_title.configure(text=self.translator.t("panel.reliability"))
        if self.reliability_var.get() in {"No prediction yet.", "暂无预测结果。"}:
            self.reliability_var.set(self.translator.t("status.no_prediction"))

    def set_reliability(self, text: str) -> None:
        self.reliability_var.set(text)
