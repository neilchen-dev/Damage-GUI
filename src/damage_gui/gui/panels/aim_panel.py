"""Aim optimization controls."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class AimPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, spread_mode_var: tk.StringVar,
                 cep_var: tk.StringVar, rep_var: tk.StringVar, dep_var: tk.StringVar,
                 rho_var: tk.StringVar, theta_var: tk.StringVar,
                 on_optimize: Callable[[], None]) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="Aim optimization", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(self, text="Spread mode", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Combobox(self, textvariable=spread_mode_var, values=("CEP", "REP_DEP"),
                     state="readonly", style="App.TCombobox").grid(
            row=1, column=1, sticky="ew", pady=2
        )
        self.cep_frame = ttk.Frame(self, style="Inspector.TFrame")
        self.cep_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._entry(self.cep_frame, "CEP", cep_var, 0, "m")
        self.rep_dep_frame = ttk.Frame(self, style="Inspector.TFrame")
        self._entry(self.rep_dep_frame, "REP", rep_var, 0, "m")
        self._entry(self.rep_dep_frame, "DEP", dep_var, 1, "m")
        self._entry(self.rep_dep_frame, "Correlation ρ", rho_var, 2)
        self._entry(self.rep_dep_frame, "Rotation θ", theta_var, 3, "°")
        self.optimize_button = ttk.Button(self, text="Optimize", command=on_optimize,
                                          style="Primary.TButton")
        self.optimize_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        self.optimize_button.bind("<Return>", lambda _event: self.optimize_button.invoke())
        self.summary_var = tk.StringVar(value="No optimization yet.")
        ttk.Label(self, textvariable=self.summary_var, style="Muted.TLabel",
                  justify="left", wraplength=220).grid(row=4, column=0, columnspan=3, sticky="ew")
        spread_mode_var.trace_add("write", lambda *_: self._toggle_mode(spread_mode_var.get()))
        self._toggle_mode(spread_mode_var.get())

    def _entry(
        self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int,
        unit: str = "",
    ) -> None:
        ttk.Label(parent, text=label, style="FieldLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 6), pady=2
        )
        input_widget = ttk.Entry(parent, textvariable=variable, style="App.TEntry")
        input_widget.grid(
            row=row, column=1, sticky="ew", pady=2
        )
        input_widget.bind(
            "<Return>", lambda _event: self.optimize_button.invoke() or "break"
        )
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
            self.optimize_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 8))
        else:
            self.cep_frame.grid_forget()
            self.rep_dep_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
            self.optimize_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 8))

    def set_summary(self, text: str) -> None:
        self.summary_var.set(text)
