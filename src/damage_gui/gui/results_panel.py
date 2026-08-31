"""Engineering-style result/property rows."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from damage_gui.gui.i18n import Translator
from damage_gui.gui.widgets import bind_tooltip


class ResultsPanel(ttk.Frame):
    """Compact property/value result inspector with no KPI cards."""

    _sections = {
        "result": ("results.result", ("maximum", "area", "grid")),
        "validation": ("results.validation", ("mean_error", "p95_error")),
        "reliability": (
            "results.reliability",
            ("confidence", "ood_distance", "inside_hull", "local_support"),
        ),
        "run": ("results.run", ("elapsed", "model")),
    }
    _labels = {
        "maximum": "results.maximum",
        "area": "results.area",
        "grid": "results.grid",
        "mean_error": "results.mean_error",
        "p95_error": "results.p95_error",
        "confidence": "results.confidence",
        "ood_distance": "results.ood_distance",
        "inside_hull": "results.inside_hull",
        "local_support": "results.local_support",
        "elapsed": "results.elapsed",
        "model": "results.model",
    }
    _full_labels = {
        "maximum": "results.maximum",
        "area": "results.area",
        "grid": "results.grid",
        "mean_error": "results.mean_error",
        "p95_error": "results.p95_error",
        "confidence": "results.confidence",
        "ood_distance": "results.ood_distance",
        "inside_hull": "results.inside_hull",
        "local_support": "results.local_support",
        "elapsed": "results.elapsed",
        "model": "results.model",
    }

    def __init__(self, parent: tk.Misc, *, translator: Translator | None = None) -> None:
        super().__init__(parent, style="Pane.TFrame", padding=(8, 8, 8, 8))
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0, minsize=82)
        self.title_label = ttk.Label(
            self, text=self.translator.t("results.title"), style="Section.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._value_labels: dict[str, ttk.Label] = {}
        self._metric_labels: list[ttk.Label] = []
        self._section_labels: dict[str, ttk.Label] = {}
        self._metric_keys: dict[str, str] = {}
        self._full_model_name = ""
        row = 1
        for _key, (section_title, keys) in self._sections.items():
            section_label = ttk.Label(
                self, text=self.translator.t(section_title), style="Section.TLabel"
            )
            section_label.grid(row=row, column=0, sticky="w", pady=(6 if row > 1 else 0, 2))
            self._section_labels[section_title] = section_label
            row += 1
            for item in keys:
                label = ttk.Label(
                    self,
                    text=self.translator.t(self._labels[item]),
                    style="FieldLabel.TLabel",
                    anchor="w",
                    justify="left",
                )
                label.grid(row=row, column=0, sticky="w", padx=(2, 0), pady=1)
                self._metric_labels.append(label)
                self._metric_keys[item] = self._labels[item]
                bind_tooltip(label, lambda item=item: self.translator.t(self._full_labels[item]))
                value = ttk.Label(self, text="—", style="Value.TLabel", anchor="e")
                value.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=1)
                if item == "model":
                    bind_tooltip(value, lambda: self._full_model_name)
                self._value_labels[item] = value
                row += 1

        self.advisory_title = ttk.Label(
            self, text=self.translator.t("results.advisory"), style="Section.TLabel"
        )
        self.advisory_title.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
        row += 1
        self.advice_label = ttk.Label(
            self,
            text=self.translator.t("results.empty_advice"),
            style="Muted.TLabel",
            justify="left",
            anchor="nw",
            wraplength=220,
        )
        self.advice_label.grid(row=row, column=0, columnspan=2, sticky="ew")
        self.bind("<Configure>", self._resize_advice)
        self.bind("<Configure>", self._resize_metric_labels, add="+")
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("results.title"))
        for key, label in self._section_labels.items():
            label.configure(text=self.translator.t(key))
        for item, label in zip(self._value_labels, self._metric_labels, strict=True):
            label.configure(text=self.translator.t(self._labels[item]))
        self.advisory_title.configure(text=self.translator.t("results.advisory"))
        if self.advice_label.cget("text") in {
            "Run training or prediction to see guidance.",
            "训练或预测完成后显示建议。",
        }:
            self.advice_label.configure(text=self.translator.t("results.empty_advice"))

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
        self.advice_label.configure(text=self.translator.t("results.empty_advice"))

    def set_advice(self, text: str) -> None:
        self.advice_label.configure(text=text)
