"""Dataset context panel."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.i18n import Translator
from damage_gui.gui.widgets import bind_tooltip, compact_path


class DatasetPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        data_dir_var: tk.StringVar,
        level_var: tk.StringVar,
        on_browse: Callable[[], None],
        translator: Translator | None = None,
    ) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.translator = translator or Translator()
        self.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(
            self, text=self.translator.t("panel.dataset"), style="Muted.TLabel"
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.directory_label = ttk.Label(
            self, text=self.translator.t("panel.directory"), style="FieldLabel.TLabel"
        )
        self.directory_label.grid(row=1, column=0, sticky="w")
        directory = ttk.Frame(self, style="Inspector.TFrame")
        directory.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        directory.columnconfigure(0, weight=1)
        self.directory_entry = ttk.Entry(directory, textvariable=data_dir_var, style="App.TEntry")
        self.directory_entry.grid(row=0, column=0, sticky="ew")
        bind_tooltip(self.directory_entry, lambda: data_dir_var.get())
        self.browse_button = ttk.Button(
            directory,
            text=self.translator.t("panel.browse"),
            command=on_browse,
            style="Secondary.TButton",
        )
        self.browse_button.grid(row=0, column=1, padx=(5, 0))

        self.level_label = ttk.Label(
            self, text=self.translator.t("panel.damage_level"), style="FieldLabel.TLabel"
        )
        self.level_label.grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            self,
            textvariable=level_var,
            values=("F", "M", "P"),
            state="readonly",
            style="App.TCombobox",
            width=8,
        ).grid(row=4, column=0, sticky="w", pady=(2, 10))
        self.summary_title = ttk.Label(
            self, text=self.translator.t("panel.dataset_summary"), style="Section.TLabel"
        )
        self.summary_title.grid(row=5, column=0, sticky="w", pady=(4, 4))
        self.summary_var = tk.StringVar(value=self.translator.t("panel.no_dataset"))
        self.summary = ttk.Label(
            self,
            textvariable=self.summary_var,
            style="Muted.TLabel",
            justify="left",
            anchor="nw",
            wraplength=220,
        )
        self.summary.grid(row=6, column=0, sticky="ew")
        self._summary_tooltip = ""
        bind_tooltip(self.summary, lambda: self._summary_tooltip)
        self.bind("<Configure>", self._resize)
        data_dir_var.trace_add(
            "write", lambda *_: self.refresh(data_dir_var.get(), level_var.get())
        )
        level_var.trace_add("write", lambda *_: self.refresh(data_dir_var.get(), level_var.get()))
        self.translator.subscribe(self.apply_language)

    def apply_language(self) -> None:
        self.title_label.configure(text=self.translator.t("panel.dataset"))
        self.directory_label.configure(text=self.translator.t("panel.directory"))
        self.level_label.configure(text=self.translator.t("panel.damage_level"))
        self.summary_title.configure(text=self.translator.t("panel.dataset_summary"))
        self.browse_button.configure(text=self.translator.t("panel.browse"))
        if not self.summary_var.get() or self.summary_var.get() in {
            "No dataset scanned yet.",
            "尚未扫描数据集。",
            "Unavailable\nCheck the selected directory.",
            "不可用\n请检查所选目录。",
        }:
            self.summary_var.set(self.translator.t("panel.no_dataset"))

    def _resize(self, event: tk.Event[tk.Misc]) -> None:
        self.summary.configure(wraplength=max(140, event.width - 10))

    def refresh(self, data_dir: str, level: str) -> None:
        try:
            from damage_gui.data.loader import DamageDataManager

            manager = DamageDataManager(data_dir)
            records = manager.scan_records()
            level_records = [record for record in records if record.level == level]
            self.summary_var.set(
                f"{self.translator.t('panel.files_discovered')}: {len(records)}\n"
                f"{self.translator.t('panel.level_samples', level=level)}: {len(level_records)}\n"
                f"{self.translator.t('panel.directory')}: {compact_path(data_dir)}"
            )
            self._summary_tooltip = f"Directory: {data_dir}"
        except (FileNotFoundError, OSError, ValueError) as exc:
            self.summary_var.set(self.translator.t("panel.unavailable"))
            self._summary_tooltip = f"Directory: {data_dir}\nError: {exc}"
