"""Export actions available in the current desktop application."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.i18n import Translator


class ExportPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_csv: Callable[[], None],
        on_png: Callable[[], None],
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.export"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.note_label = ttk.Label(
            self,
            text=self.translator.t("panel.export_note"),
            style="Muted.TLabel",
            justify="left",
            wraplength=220,
        )
        self.note_label.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.csv_button = ttk.Button(
            self,
            text=self.translator.t("panel.export_csv"),
            command=on_csv,
            style="Secondary.TButton",
        )
        self.csv_button.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        self.png_button = ttk.Button(
            self,
            text=self.translator.t("panel.export_png"),
            command=on_png,
            style="Secondary.TButton",
        )
        self.png_button.grid(row=3, column=0, sticky="ew")
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.export"))
        self.note_label.configure(text=self.translator.t("panel.export_note"))
        self.csv_button.configure(text=self.translator.t("panel.export_csv"))
        self.png_button.configure(text=self.translator.t("panel.export_png"))
