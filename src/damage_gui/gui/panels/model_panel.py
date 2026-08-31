"""Model configuration and lifecycle controls."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.i18n import Translator
from damage_gui.gui.presentation import model_type_choices, validation_choices


class ModelPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        model_type_var: tk.StringVar,
        pod_components_var: tk.StringVar,
        validation_var: tk.StringVar,
        on_train: Callable[[], None],
        on_cancel: Callable[[], None],
        on_load: Callable[[], None],
        on_save: Callable[[], None],
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.model"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.model_type_label = self._field_label("panel.model_type", 1)
        self.model_type_combo = ttk.Combobox(
            self,
            textvariable=model_type_var,
            values=[label for label, _ in model_type_choices(self.translator)],
            state="readonly",
            style="App.TCombobox",
        )
        self.model_type_combo.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        self.pod_label = self._field_label("panel.pod_components", 3)
        ttk.Spinbox(
            self,
            textvariable=pod_components_var,
            from_=2,
            to=200,
            increment=1,
            style="App.TSpinbox",
        ).grid(row=4, column=0, sticky="ew", pady=(2, 8))
        self.validation_label = self._field_label("panel.validation_mode", 5)
        self.validation_combo = ttk.Combobox(
            self,
            textvariable=validation_var,
            values=[label for label, _ in validation_choices(self.translator)],
            state="readonly",
            style="App.TCombobox",
        )
        self.validation_combo.grid(row=6, column=0, sticky="ew", pady=(2, 10))
        self.status_title = ttk.Label(
            self, text=self.translator.t("panel.model_status"), style="Section.TLabel"
        )
        self.status_title.grid(row=7, column=0, sticky="w", pady=(4, 4))
        self.status_var = tk.StringVar(value=self.translator.t("panel.no_model_yet"))
        ttk.Label(
            self, textvariable=self.status_var, style="Muted.TLabel", justify="left", wraplength=220
        ).grid(row=8, column=0, sticky="ew")

        self.train_button = ttk.Button(
            self, text=self.translator.t("panel.train"), command=on_train, style="Primary.TButton"
        )
        self.train_button.grid(row=9, column=0, sticky="ew", pady=(10, 5))
        self.train_button.bind("<Return>", lambda _event: self.train_button.invoke())
        secondary = ttk.Frame(self, style="Inspector.TFrame")
        secondary.grid(row=10, column=0, sticky="ew")
        secondary.columnconfigure((0, 1), weight=1)
        self.cancel_button = ttk.Button(
            secondary,
            text=self.translator.t("panel.cancel"),
            command=on_cancel,
            style="Secondary.TButton",
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.load_button = ttk.Button(
            secondary,
            text=self.translator.t("panel.load"),
            command=on_load,
            style="Secondary.TButton",
        )
        self.load_button.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.save_button = ttk.Button(
            self, text=self.translator.t("panel.save"), command=on_save, style="Secondary.TButton"
        )
        self.save_button.grid(row=11, column=0, sticky="ew", pady=(5, 0))

        self.translator.subscribe(self.apply_language)

    def _field_label(self, key: str, row: int) -> ttk.Label:
        label = ttk.Label(self, text=self.translator.t(key), style="FieldLabel.TLabel")
        label.grid(row=row, column=0, sticky="w")
        return label

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.model"))
        self.model_type_label.configure(text=self.translator.t("panel.model_type"))
        self.pod_label.configure(text=self.translator.t("panel.pod_components"))
        self.validation_label.configure(text=self.translator.t("panel.validation_mode"))
        self.status_title.configure(text=self.translator.t("panel.model_status"))
        self.train_button.configure(text=self.translator.t("panel.train"))
        self.cancel_button.configure(text=self.translator.t("panel.cancel"))
        self.load_button.configure(text=self.translator.t("panel.load"))
        self.save_button.configure(text=self.translator.t("panel.save"))
        self.model_type_combo.configure(
            values=[label for label, _ in model_type_choices(self.translator)]
        )
        self.validation_combo.configure(
            values=[label for label, _ in validation_choices(self.translator)]
        )

    def set_model_status(self, text: str) -> None:
        self.status_var.set(text)
