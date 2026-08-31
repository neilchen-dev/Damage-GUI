"""History context panel preserving the existing traceability scope."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from damage_gui.gui.i18n import Translator
from damage_gui.gui.widgets import bind_tooltip, compact_path


class HistoryPanel(ttk.Frame):
    def __init__(
        self, parent: tk.Misc, *, db_path: str, translator: Translator | None = None
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self._db_path = db_path
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.history"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.note_label = ttk.Label(
            self,
            text=self.translator.t("panel.history_note"),
            style="Muted.TLabel",
            justify="left",
            wraplength=220,
        )
        self.note_label.grid(row=1, column=0, sticky="ew")
        self.database_title = ttk.Label(
            self, text=self.translator.t("panel.database"), style="FieldLabel.TLabel"
        )
        self.database_title.grid(row=2, column=0, sticky="w", pady=(12, 3))
        self.database_label = ttk.Label(
            self, text=compact_path(db_path), style="Value.TLabel", anchor="w"
        )
        self.database_label.grid(row=3, column=0, sticky="ew")
        bind_tooltip(self.database_label, db_path)
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.history"))
        self.note_label.configure(text=self.translator.t("panel.history_note"))
        self.database_title.configure(text=self.translator.t("panel.database"))
