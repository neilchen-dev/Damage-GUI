"""Compact navigation tree for the desktop workbench."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

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


class NavigationPanel(ttk.Frame):
    """Tree-based navigation that switches the contextual inspector."""

    def __init__(self, parent: tk.Misc, on_select: Callable[[str], None]) -> None:
        super().__init__(parent, style="Pane.TFrame", padding=(8, 8, 6, 8))
        self._on_select = on_select
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Navigation", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.tree = ttk.Treeview(
            self,
            show="tree",
            selectmode="browse",
            style="Navigation.Treeview",
            takefocus=True,
        )
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._handle_select)

        self._add_section("project", "Project", ("dataset", "model", "validation"))
        self._add_section("analysis", "Analysis", ("prediction", "batch", "aim"))
        self._add_section("results", "Results", ("history", "export"))
        self.select("dataset")

    def _add_section(self, section_id: str, title: str, children: tuple[str, ...]) -> None:
        self.tree.insert("", "end", iid=section_id, text=title, open=True, tags=("section",))
        for key in children:
            self.tree.insert(section_id, "end", iid=key, text=NAVIGATION_LABELS[key])

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
