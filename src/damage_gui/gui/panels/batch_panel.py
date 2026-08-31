"""Batch prediction controls."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.i18n import Translator
from damage_gui.gui.widgets import bind_tooltip, compact_path


class BatchPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        csv_var: tk.StringVar,
        on_browse: Callable[[], None],
        on_run: Callable[[], None],
        on_cancel: Callable[[], None],
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.batch"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.input_label = ttk.Label(
            self, text=self.translator.t("panel.input_csv"), style="FieldLabel.TLabel"
        )
        self.input_label.grid(row=1, column=0, sticky="w")
        path_row = ttk.Frame(self, style="Inspector.TFrame")
        path_row.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        path_row.columnconfigure(0, weight=1)
        ttk.Entry(path_row, textvariable=csv_var, style="App.TEntry").grid(
            row=0, column=0, sticky="ew"
        )
        self.browse_button = ttk.Button(
            path_row,
            text=self.translator.t("panel.browse"),
            command=on_browse,
            style="Secondary.TButton",
        )
        self.browse_button.grid(row=0, column=1, padx=(5, 0))
        self.info_var = tk.StringVar(value=self.translator.t("panel.no_batch_file"))
        self.info_label = ttk.Label(
            self,
            textvariable=self.info_var,
            style="Muted.TLabel",
            justify="left",
            wraplength=220,
        )
        self.info_label.grid(row=3, column=0, sticky="ew")
        self._full_info = ""
        bind_tooltip(self.info_label, lambda: self._full_info)
        self.run_button = ttk.Button(
            self, text=self.translator.t("panel.run_batch"), command=on_run, style="Primary.TButton"
        )
        self.run_button.grid(row=4, column=0, sticky="ew", pady=(10, 5))
        self.run_button.bind("<Return>", lambda _event: self.run_button.invoke())
        self.cancel_button = ttk.Button(
            self,
            text=self.translator.t("panel.cancel"),
            command=on_cancel,
            style="Secondary.TButton",
            state="disabled",
        )
        self.cancel_button.grid(row=5, column=0, sticky="ew")
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.batch"))
        self.input_label.configure(text=self.translator.t("panel.input_csv"))
        self.browse_button.configure(text=self.translator.t("panel.browse"))
        self.run_button.configure(text=self.translator.t("panel.run_batch"))
        self.cancel_button.configure(text=self.translator.t("panel.cancel"))
        if self.info_var.get() in {"No batch file selected yet.", "尚未选择批量文件。"}:
            self.info_var.set(self.translator.t("panel.no_batch_file"))

    def set_info(self, text: str, *, full_text: str = "") -> None:
        self.info_var.set(text)
        self._full_info = full_text

    def set_selected_path(self, path: str) -> None:
        self.set_info(f"Selected: {compact_path(path)}", full_text=f"Selected: {path}")
