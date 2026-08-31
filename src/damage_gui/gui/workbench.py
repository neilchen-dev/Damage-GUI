"""Top-level four-pane desktop workbench shell."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont
from tkinter import ttk

from damage_gui.gui.i18n import Translator
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
        translator: Translator,
        callbacks: dict[str, Callable[[], None]],
        on_navigate: Callable[[str], None],
        on_view_change: Callable[[str], None],
        on_language: Callable[[str], None],
    ) -> None:
        self.root = root
        self.theme = theme
        self.callbacks = callbacks
        self.translator = translator
        self._on_language = on_language
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
        old_menu = getattr(self, "_menu", None)
        if old_menu is not None:
            try:
                old_menu.destroy()
            except tk.TclError:
                pass
        menu = tk.Menu(self.root, tearoff=False, font=self._menu_font)
        file_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        file_menu.add_command(
            label=self.translator.t("menu.open_model"), command=self._callback("load")
        )
        file_menu.add_command(
            label=self.translator.t("menu.save_model"), command=self._callback("save")
        )
        file_menu.add_separator()
        file_menu.add_command(
            label=self.translator.t("menu.export_csv"), command=self._callback("export_csv")
        )
        file_menu.add_command(
            label=self.translator.t("menu.export_png"), command=self._callback("export_png")
        )
        file_menu.add_separator()
        file_menu.add_command(label=self.translator.t("menu.exit"), command=self._callback("close"))
        menu.add_cascade(label=self.translator.t("menu.file"), menu=file_menu)

        view_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        view_menu.add_command(
            label=self.translator.t("menu.dataset"),
            command=lambda: self._callback("navigate_dataset")(),
        )
        view_menu.add_command(
            label=self.translator.t("menu.prediction"),
            command=lambda: self._callback("navigate_prediction")(),
        )
        view_menu.add_command(label=self.translator.t("menu.reset_panes"), command=self.reset_panes)
        menu.add_cascade(label=self.translator.t("menu.view"), menu=view_menu)

        model_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        model_menu.add_command(
            label=self.translator.t("menu.train"), command=self._callback("train")
        )
        model_menu.add_command(
            label=self.translator.t("menu.cancel_training"),
            command=self._callback("cancel_training"),
        )
        model_menu.add_command(
            label=self.translator.t("menu.open_model"), command=self._callback("load")
        )
        model_menu.add_command(
            label=self.translator.t("menu.save_model"), command=self._callback("save")
        )
        menu.add_cascade(label=self.translator.t("menu.model"), menu=model_menu)

        analysis_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        analysis_menu.add_command(
            label=self.translator.t("menu.run_prediction"), command=self._callback("predict")
        )
        analysis_menu.add_command(
            label=self.translator.t("menu.batch_prediction"),
            command=self._callback("navigate_batch"),
        )
        analysis_menu.add_command(
            label=self.translator.t("menu.aim"), command=self._callback("navigate_aim")
        )
        analysis_menu.add_separator()
        analysis_menu.add_command(
            label=self.translator.t("menu.stop"), command=self._callback("stop")
        )
        menu.add_cascade(label=self.translator.t("menu.analysis"), menu=analysis_menu)

        results_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        results_menu.add_command(
            label=self.translator.t("menu.history"), command=self._callback("navigate_history")
        )
        results_menu.add_command(
            label=self.translator.t("menu.export"), command=self._callback("navigate_export")
        )
        menu.add_cascade(label=self.translator.t("menu.results"), menu=results_menu)

        help_menu = tk.Menu(menu, tearoff=False, font=self._menu_font)
        help_menu.add_command(label=self.translator.t("menu.help_about"), command=lambda: None)
        menu.add_cascade(label=self.translator.t("menu.help"), menu=help_menu)
        self.root.configure(menu=menu)
        self._menu = menu

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(8, 3))
        toolbar.grid(row=1, column=0, sticky="ew")
        self.open_button = ttk.Button(
            toolbar,
            text=self.translator.t("toolbar.open"),
            command=self._callback("load"),
            style="Toolbar.TButton",
        )
        self.open_button.pack(side="left")
        self.save_button = ttk.Button(
            toolbar,
            text=self.translator.t("toolbar.save"),
            command=self._callback("save"),
            style="Toolbar.TButton",
        )
        self.save_button.pack(side="left", padx=(4, 0))
        self.run_button = ttk.Button(
            toolbar,
            text=self.translator.t("toolbar.run"),
            command=self._callback("predict"),
            style="Primary.TButton",
        )
        self.run_button.pack(side="left", padx=(12, 0))
        self.run_button.bind("<Return>", lambda _event: self.run_button.invoke())
        self.stop_button = ttk.Button(
            toolbar,
            text=self.translator.t("toolbar.stop"),
            command=self._callback("stop"),
            style="Toolbar.TButton",
        )
        self.stop_button.pack(side="left", padx=(4, 0))
        self.language_label = ttk.Label(
            toolbar, text=self.translator.t("language.label"), style="Status.TLabel"
        )
        self.language_label.pack(side="right", padx=(14, 5))
        self.language_var = tk.StringVar(value=self.translator.language_label())
        self.language_combo = ttk.Combobox(
            toolbar,
            textvariable=self.language_var,
            values=self.translator.language_choices(),
            state="readonly",
            width=9,
            style="Toolbar.TCombobox",
        )
        self.language_combo.pack(side="right")
        self.language_combo.bind("<<ComboboxSelected>>", self._handle_language_change)

    def _handle_language_change(self, _event: object = None) -> None:
        language = self.translator.language_from_label(self.language_var.get())
        if language is not None:
            self._on_language(language)

    def apply_language(self) -> None:
        self.open_button.configure(text=self.translator.t("toolbar.open"))
        self.save_button.configure(text=self.translator.t("toolbar.save"))
        self.run_button.configure(text=self.translator.t("toolbar.run"))
        self.stop_button.configure(text=self.translator.t("toolbar.stop"))
        self.language_label.configure(text=self.translator.t("language.label"))
        self.language_combo.configure(values=self.translator.language_choices())
        self.language_var.set(self.translator.language_label())
        self._build_menu()

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
        self.navigation = NavigationPanel(self.panes, on_navigate, translator=self.translator)
        self.properties = PropertiesHost(self.panes)
        self.visualization = VisualizationPanel(
            self.panes, on_view_change, translator=self.translator
        )
        self.results = ResultsPanel(self.panes, translator=self.translator)
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
        self.status = StatusBar(self.root, translator=self.translator)
        self.status.grid(row=3, column=0, sticky="ew")
        self.root.rowconfigure(2, weight=1)
        self.root.after_idle(self._reset_when_ready)
        self.translator.subscribe(self.apply_language)

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
