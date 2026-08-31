"""Top-level four-pane desktop workbench shell."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from tkinter import ttk

from damage_gui.gui.navigation import NavigationPanel
from damage_gui.gui.results_panel import ResultsPanel
from damage_gui.gui.status_bar import StatusBar
from damage_gui.gui.theme import THEME, Theme, resolve_font_families
from damage_gui.gui.visualization_panel import VisualizationPanel


class PropertiesHost(ttk.Frame):
    """One contextual inspector slot shared by all navigation items."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Inspector.TFrame", padding=(10, 8, 8, 8))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.title_var = tk.StringVar(value="Properties")
        ttk.Label(self, textvariable=self.title_var, style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.body = ttk.Frame(self, style="Inspector.TFrame")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)
        self._panels: dict[str, ttk.Frame] = {}

    def add(self, key: str, panel: ttk.Frame) -> None:
        self._panels[key] = panel

    def show(self, key: str, title: str) -> None:
        panel = self._panels.get(key)
        if panel is None:
            return
        for child in self.body.winfo_children():
            child.grid_forget()
        self.title_var.set(title)
        panel.grid(row=0, column=0, sticky="nsew")


class WorkbenchShell:
    """Construct the menu, toolbar, resizable panes, and status bar."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        theme: Theme = THEME,
        callbacks: dict[str, Callable[[], None]],
        on_navigate: Callable[[str], None],
        on_view_change: Callable[[str], None],
    ) -> None:
        self.root = root
        self.theme = theme
        self.callbacks = callbacks
        try:
            self._menu_font = (resolve_font_families(tkfont.families(root), theme).latin, 10)
        except tk.TclError:
            self._menu_font = (theme.ui_latin_font, 10)
        self._build_menu()
        self._build_toolbar()
        self._build_panes(on_navigate, on_view_change)

    def _callback(self, key: str) -> Callable[[], None]:
        return self.callbacks.get(key, lambda: None)

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=False, font=self._menu_font)
        file_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        file_menu.add_command(label="Open Model…", command=self._callback("load"))
        file_menu.add_command(label="Save Model…", command=self._callback("save"))
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV…", command=self._callback("export_csv"))
        file_menu.add_command(label="Export PNG…", command=self._callback("export_png"))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._callback("close"))
        menu.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        view_menu.add_command(label="Dataset", command=lambda: self._callback("navigate_dataset")())
        view_menu.add_command(
            label="Prediction", command=lambda: self._callback("navigate_prediction")()
        )
        view_menu.add_command(label="Reset Pane Sizes", command=self.reset_panes)
        menu.add_cascade(label="View", menu=view_menu)

        model_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        model_menu.add_command(label="Train Model", command=self._callback("train"))
        model_menu.add_command(label="Cancel Training", command=self._callback("cancel_training"))
        model_menu.add_command(label="Load Model…", command=self._callback("load"))
        model_menu.add_command(label="Save Model…", command=self._callback("save"))
        menu.add_cascade(label="Model", menu=model_menu)

        analysis_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        analysis_menu.add_command(label="Run Prediction", command=self._callback("predict"))
        analysis_menu.add_command(
            label="Batch Prediction", command=self._callback("navigate_batch")
        )
        analysis_menu.add_command(label="Aim Optimization", command=self._callback("navigate_aim"))
        analysis_menu.add_separator()
        analysis_menu.add_command(label="Stop Current Task", command=self._callback("stop"))
        menu.add_cascade(label="Analysis", menu=analysis_menu)

        results_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        results_menu.add_command(label="History", command=self._callback("navigate_history"))
        results_menu.add_command(label="Export", command=self._callback("navigate_export"))
        menu.add_cascade(label="Results", menu=results_menu)
        self.root.configure(menu=menu)

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(8, 3))
        toolbar.grid(row=1, column=0, sticky="ew")
        self.open_button = ttk.Button(toolbar, text="Open", command=self._callback("load"),
                                      style="Toolbar.TButton")
        self.open_button.pack(side="left")
        self.save_button = ttk.Button(toolbar, text="Save", command=self._callback("save"),
                                      style="Toolbar.TButton")
        self.save_button.pack(side="left", padx=(4, 0))
        self.run_button = ttk.Button(toolbar, text="Run", command=self._callback("predict"),
                                     style="Primary.TButton")
        self.run_button.pack(side="left", padx=(12, 0))
        self.run_button.bind("<Return>", lambda _event: self.run_button.invoke())
        self.stop_button = ttk.Button(toolbar, text="Stop", command=self._callback("stop"),
                                      style="Toolbar.TButton")
        self.stop_button.pack(side="left", padx=(4, 0))

    def _build_panes(
        self,
        on_navigate: Callable[[str], None],
        on_view_change: Callable[[str], None],
    ) -> None:
        body = ttk.Frame(self.root, style="Workbench.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.panes = ttk.PanedWindow(body, orient="horizontal")
        self.panes.grid(row=0, column=0, sticky="nsew")
        self.navigation = NavigationPanel(self.panes, on_navigate)
        self.properties = PropertiesHost(self.panes)
        self.visualization = VisualizationPanel(self.panes, on_view_change)
        self.results = ResultsPanel(self.panes)
        for child, weight in (
            (self.navigation, 1),
            (self.properties, 1),
            (self.visualization, 4),
            (self.results, 1),
        ):
            try:
                self.panes.add(child, weight=weight)
            except tk.TclError:
                self.panes.add(child)
        self.status = StatusBar(self.root)
        self.status.grid(row=3, column=0, sticky="ew")
        self.root.rowconfigure(2, weight=1)
        self.root.after_idle(self._reset_when_ready)

    def reset_panes(self) -> None:
        self.root.update_idletasks()
        width = self.panes.winfo_width()
        if width < 800:
            return
        positions = (200, 470, max(720, width - 240))
        for index, position in enumerate(positions):
            try:
                self.panes.sashpos(index, position)
            except tk.TclError:
                break

    def _reset_when_ready(self) -> None:
        if self.panes.winfo_width() < 800:
            self.root.after(50, self._reset_when_ready)
        else:
            self.reset_panes()
