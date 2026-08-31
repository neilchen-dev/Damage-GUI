"""Engineering-style result/property rows."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from damage_gui.gui.widgets import bind_tooltip


class ResultsPanel(ttk.Frame):
    """Compact property/value result inspector with no KPI cards."""

    _sections = {
        "result": ("Result", ("maximum", "area", "grid")),
        "validation": ("Validation", ("mean_error", "p95_error")),
        "reliability": (
            "Reliability", ("confidence", "ood_distance", "inside_hull", "local_support")
        ),
        "run": ("Run info", ("elapsed", "model")),
    }
    _labels = {
        "maximum": "Maximum",
        "area": "Area",
        "grid": "Grid",
        "mean_error": "Mean Rel.",
        "p95_error": "P95 Error",
        "confidence": "Confidence",
        "ood_distance": "OOD Dist.",
        "inside_hull": "Inside Hull",
        "local_support": "Local Supp.",
        "elapsed": "Elapsed",
        "model": "Model",
    }
    _full_labels = {
        "maximum": "Maximum Damage",
        "area": "Damaged Area",
        "grid": "Grid",
        "mean_error": "Mean Relative Error",
        "p95_error": "P95 Hybrid Error",
        "confidence": "Confidence",
        "ood_distance": "OOD Distance",
        "inside_hull": "Inside Hull",
        "local_support": "Local Support",
        "elapsed": "Elapsed",
        "model": "Model",
    }

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Pane.TFrame", padding=(8, 8, 8, 8))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=82)
        ttk.Label(self, text="Results", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self._value_labels: dict[str, ttk.Label] = {}
        self._metric_labels: list[ttk.Label] = []
        self._full_model_name = ""
        row = 1
        for _key, (section_title, keys) in self._sections.items():
            ttk.Label(self, text=section_title, style="Section.TLabel").grid(
                row=row, column=0, sticky="w", pady=(6 if row > 1 else 0, 2)
            )
            row += 1
            for item in keys:
                label = ttk.Label(
                    self,
                    text=self._labels[item],
                    style="FieldLabel.TLabel",
                    anchor="w",
                    justify="left",
                )
                label.grid(
                    row=row, column=0, sticky="w", padx=(2, 0), pady=1
                )
                self._metric_labels.append(label)
                if self._labels[item] != self._full_labels[item]:
                    bind_tooltip(label, self._full_labels[item])
                value = ttk.Label(self, text="—", style="Value.TLabel", anchor="e")
                value.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=1)
                if item == "model":
                    bind_tooltip(value, lambda: self._full_model_name)
                self._value_labels[item] = value
                row += 1

        ttk.Label(self, text="Advisory", style="Section.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 2)
        )
        row += 1
        self.advice_label = ttk.Label(
            self, text="Run training or prediction to see guidance.", style="Muted.TLabel",
            justify="left", anchor="nw", wraplength=220,
        )
        self.advice_label.grid(row=row, column=0, columnspan=2, sticky="ew")
        self.bind("<Configure>", self._resize_advice)
        self.bind("<Configure>", self._resize_metric_labels, add="+")

    def _resize_metric_labels(self, _event: tk.Event[tk.Misc]) -> None:
        """Wrap technical labels only when a high-DPI pane needs it."""
        try:
            label_width = self.grid_bbox(0, 1, 0, 1)[2]
        except tk.TclError:
            return
        wraplength = max(72, label_width - 4)
        for label in self._metric_labels:
            label.configure(wraplength=wraplength)

    def _resize_advice(self, event: tk.Event[tk.Misc]) -> None:
        self.advice_label.configure(wraplength=max(120, event.width - 22))

    def set_value(self, key: str, value: Any, *, color: str | None = None) -> None:
        label = self._value_labels.get(key)
        if label is None:
            return
        display = "—" if value is None else str(value)
        if key == "model":
            self._full_model_name = "" if value is None else display
            if len(display) > 10:
                display = f"{display[:4]}…{display[-4:]}"
        label.configure(text=display)
        if color is not None:
            label.configure(foreground=color)

    def reset(self) -> None:
        for key in self._value_labels:
            self.set_value(key, None)
        self.advice_label.configure(text="Run training or prediction to see guidance.")

    def set_advice(self, text: str) -> None:
        self.advice_label.configure(text=text)
