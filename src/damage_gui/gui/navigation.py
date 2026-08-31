"""Compact navigation tree for the desktop workbench."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.i18n import Translator

NAVIGATION_LABELS = {
    "dataset": "Dataset",
    "model": "Model",
    "validation": "Validation",
    "prediction": "Prediction",
    "batch": "Batch Prediction",
    "aim": "Aim Optimization",
    "history": "History",
    "export": "Export",
}

NAVIGATION_KEYS = tuple(NAVIGATION_LABELS)


class NavigationPanel(ttk.Frame):
    """Tree-based navigation that switches the contextual inspector."""

    def __init__(
        self,
        parent: tk.Misc,
        on_select: Callable[[str], None],
        *,
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Pane.TFrame", padding=(8, 8, 6, 8))
        self.translator = translator or Translator()
        self._on_select = on_select
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.title_label = ttk.Label(
            self, text=self.translator.t("navigation.title"), style="Section.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.tree = ttk.Treeview(
            self,
            show="tree",
            selectmode="browse",
            style="Navigation.Treeview",
            takefocus=True,
        )
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._handle_select)

        self._sections = {
            "project": ("navigation.project", ("dataset", "model", "validation")),
            "analysis": ("navigation.analysis", ("prediction", "batch", "aim")),
            "results": ("navigation.results", ("history", "export")),
        }
        for section_id, (title_key, children) in self._sections.items():
            self._add_section(section_id, title_key, children)
        self.select("dataset")
        self.translator.subscribe(self.apply_language)

    def _add_section(self, section_id: str, title_key: str, children: tuple[str, ...]) -> None:
        self.tree.insert(
            "",
            "end",
            iid=section_id,
            text=self.translator.t(title_key),
            open=True,
            tags=("section",),
        )
        for key in children:
            self.tree.insert(section_id, "end", iid=key, text=self.translator.t(f"nav.{key}"))

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("navigation.title"))
        for section_id, (title_key, children) in self._sections.items():
            self.tree.item(section_id, text=self.translator.t(title_key))
            for key in children:
                self.tree.item(key, text=self.translator.t(f"nav.{key}"))

    def _handle_select(self, _event: object = None) -> None:
        selected = self.tree.selection()
        if not selected or selected[0] not in NAVIGATION_LABELS:
            return
        self._on_select(selected[0])

    def select(self, key: str) -> None:
        if key not in NAVIGATION_LABELS:
            return
        if self.tree.selection() != (key,):
            self.tree.selection_set(key)
        self.tree.focus(key)
        self.tree.see(key)
