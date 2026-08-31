"""Aim optimization controls."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.i18n import Translator


class AimPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        spread_mode_var: tk.StringVar,
        cep_var: tk.StringVar,
        rep_var: tk.StringVar,
        dep_var: tk.StringVar,
        rho_var: tk.StringVar,
        theta_var: tk.StringVar,
        on_optimize: Callable[[], None],
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.aim"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.mode_label = ttk.Label(
            self, text=self.translator.t("panel.spread_mode"), style="FieldLabel.TLabel"
        )
        self.mode_label.grid(row=1, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(
            self,
            textvariable=spread_mode_var,
            values=("CEP", "REP / DEP"),
            state="readonly",
            style="App.TCombobox",
        )
        self.mode_combo.grid(row=1, column=1, sticky="ew", pady=2)
        self.cep_frame = ttk.Frame(self, style="Inspector.TFrame")
        self.cep_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._entry(self.cep_frame, "panel.cep", cep_var, 0, "m")
        self.rep_dep_frame = ttk.Frame(self, style="Inspector.TFrame")
        self._entry(self.rep_dep_frame, "panel.rep", rep_var, 0, "m")
        self._entry(self.rep_dep_frame, "panel.dep", dep_var, 1, "m")
        self._entry(self.rep_dep_frame, "panel.correlation", rho_var, 2)
        self._entry(self.rep_dep_frame, "panel.rotation", theta_var, 3, "°")
        self.optimize_button = ttk.Button(
            self,
            text=self.translator.t("panel.optimize"),
            command=on_optimize,
            style="Primary.TButton",
        )
        self.optimize_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        self.optimize_button.bind("<Return>", lambda _event: self.optimize_button.invoke())
        self.summary_var = tk.StringVar(value=self.translator.t("status.no_optimization"))
        ttk.Label(
            self,
            textvariable=self.summary_var,
            style="Muted.TLabel",
            justify="left",
            wraplength=220,
        ).grid(row=4, column=0, columnspan=3, sticky="ew")
        spread_mode_var.trace_add("write", lambda *_: self._toggle_mode(spread_mode_var.get()))
        self._toggle_mode(spread_mode_var.get())
        self.translator.subscribe(self.apply_language)

    def _entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        row: int,
        unit: str = "",
    ) -> None:
        label_widget = ttk.Label(parent, text=self.translator.t(label), style="FieldLabel.TLabel")
        label_widget.grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        if not hasattr(self, "_field_labels"):
            self._field_labels = {}
        self._field_labels[label] = label_widget
        input_widget = ttk.Entry(parent, textvariable=variable, style="App.TEntry")
        input_widget.grid(row=row, column=1, sticky="ew", pady=2)
        input_widget.bind("<Return>", lambda _event: self.optimize_button.invoke() or "break")
        if unit:
            ttk.Label(parent, text=unit, style="Unit.TLabel").grid(
                row=row, column=2, sticky="w", padx=(6, 0)
            )
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, minsize=28)

    def _toggle_mode(self, mode: str) -> None:
        if mode == "CEP":
            self.rep_dep_frame.grid_forget()
            self.cep_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        else:
            self.cep_frame.grid_forget()
            self.rep_dep_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.optimize_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 8))

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.aim"))
        self.mode_label.configure(text=self.translator.t("panel.spread_mode"))
        self.optimize_button.configure(text=self.translator.t("panel.optimize"))
        for key, label in self._field_labels.items():
            label.configure(text=self.translator.t(key))
        if self.summary_var.get() in {"No optimization yet.", "暂无优化结果。"}:
            self.summary_var.set(self.translator.t("status.no_optimization"))

    def set_summary(self, text: str) -> None:
        self.summary_var.set(text)
