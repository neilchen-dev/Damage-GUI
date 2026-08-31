"""Dataset context panel."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from damage_gui.gui.widgets import bind_tooltip, compact_path


class DatasetPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, data_dir_var: tk.StringVar,
                 level_var: tk.StringVar, on_browse: Callable[[], None]) -> None:
        super().__init__(parent, style="Inspector.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Dataset configuration", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(self, text="Directory", style="FieldLabel.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        directory = ttk.Frame(self, style="Inspector.TFrame")
        directory.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        directory.columnconfigure(0, weight=1)
        self.directory_entry = ttk.Entry(
            directory, textvariable=data_dir_var, style="App.TEntry"
        )
        self.directory_entry.grid(
            row=0, column=0, sticky="ew"
        )
        bind_tooltip(self.directory_entry, lambda: data_dir_var.get())
        ttk.Button(directory, text="Browse…", command=on_browse,
                   style="Secondary.TButton").grid(row=0, column=1, padx=(5, 0))

        ttk.Label(self, text="Damage level", style="FieldLabel.TLabel").grid(
            row=3, column=0, sticky="w"
        )
        ttk.Combobox(self, textvariable=level_var, values=("F", "M", "P"),
                     state="readonly", style="App.TCombobox", width=8).grid(
            row=4, column=0, sticky="w", pady=(2, 10)
        )
        ttk.Label(self, text="Dataset summary", style="Section.TLabel").grid(
            row=5, column=0, sticky="w", pady=(4, 4)
        )
        self.summary_var = tk.StringVar(value="No dataset scanned yet.")
        self.summary = ttk.Label(self, textvariable=self.summary_var, style="Muted.TLabel",
                                 justify="left", anchor="nw", wraplength=220)
        self.summary.grid(row=6, column=0, sticky="ew")
        self._summary_tooltip = ""
        bind_tooltip(self.summary, lambda: self._summary_tooltip)
        self.bind("<Configure>", self._resize)
        data_dir_var.trace_add(
            "write", lambda *_: self.refresh(data_dir_var.get(), level_var.get())
        )
        level_var.trace_add("write", lambda *_: self.refresh(data_dir_var.get(), level_var.get()))

    def _resize(self, event: tk.Event[tk.Misc]) -> None:
        self.summary.configure(wraplength=max(140, event.width - 10))

    def refresh(self, data_dir: str, level: str) -> None:
        try:
            from damage_gui.data.loader import DamageDataManager

            manager = DamageDataManager(data_dir)
            records = manager.scan_records()
            level_records = [record for record in records if record.level == level]
            self.summary_var.set(
                f"Files discovered: {len(records)}\n"
                f"Level {level}: {len(level_records)} samples\n"
                f"Directory: {compact_path(data_dir)}"
            )
            self._summary_tooltip = f"Directory: {data_dir}"
        except (FileNotFoundError, OSError, ValueError) as exc:
            self.summary_var.set("Unavailable\nCheck the selected directory.")
            self._summary_tooltip = f"Directory: {data_dir}\nError: {exc}"
