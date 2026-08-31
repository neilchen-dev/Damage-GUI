"""Model configuration and lifecycle controls."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.presentation import MODEL_TYPE_CHOICES, VALIDATION_CHOICES


class ModelPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, model_type_var: tk.StringVar,
                 pod_components_var: tk.StringVar, validation_var: tk.StringVar,
                 on_train: Callable[[], None], on_cancel: Callable[[], None],
                 on_load: Callable[[], None], on_save: Callable[[], None]) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Model configuration", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self._field_label("Model type", 1)
        ttk.Combobox(self, textvariable=model_type_var,
                     values=[label for label, _ in MODEL_TYPE_CHOICES],
                     state="readonly", style="App.TCombobox").grid(
            row=2, column=0, sticky="ew", pady=(2, 8)
        )
        self._field_label("POD components K", 3)
        ttk.Spinbox(self, textvariable=pod_components_var, from_=2, to=200,
                    increment=1, style="App.TSpinbox").grid(
            row=4, column=0, sticky="ew", pady=(2, 8)
        )
        self._field_label("Validation mode", 5)
        ttk.Combobox(self, textvariable=validation_var,
                     values=[label for label, _ in VALIDATION_CHOICES],
                     state="readonly", style="App.TCombobox").grid(
            row=6, column=0, sticky="ew", pady=(2, 10)
        )
        ttk.Label(self, text="Model status", style="Section.TLabel").grid(
            row=7, column=0, sticky="w", pady=(4, 4)
        )
        self.status_var = tk.StringVar(value="No model loaded yet.")
        ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel",
                  justify="left", wraplength=220).grid(row=8, column=0, sticky="ew")

        self.train_button = ttk.Button(self, text="Train Model", command=on_train,
                                       style="Primary.TButton")
        self.train_button.grid(row=9, column=0, sticky="ew", pady=(10, 5))
        self.train_button.bind("<Return>", lambda _event: self.train_button.invoke())
        secondary = ttk.Frame(self, style="Inspector.TFrame")
        secondary.grid(row=10, column=0, sticky="ew")
        secondary.columnconfigure((0, 1), weight=1)
        self.cancel_button = ttk.Button(secondary, text="Cancel", command=on_cancel,
                                        style="Secondary.TButton", state="disabled")
        self.cancel_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.load_button = ttk.Button(secondary, text="Load", command=on_load,
                                      style="Secondary.TButton")
        self.load_button.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.save_button = ttk.Button(self, text="Save", command=on_save,
                                      style="Secondary.TButton")
        self.save_button.grid(row=11, column=0, sticky="ew", pady=(5, 0))

    def _field_label(self, text: str, row: int) -> None:
        ttk.Label(self, text=text, style="FieldLabel.TLabel").grid(
            row=row, column=0, sticky="w"
        )

    def set_model_status(self, text: str) -> None:
        self.status_var.set(text)
