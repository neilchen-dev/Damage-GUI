"""Central scientific visualization viewport."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from damage_gui.gui.dpi import get_window_dpi

VIEW_LABELS = {
    "triple": "对比三联图",
    "full": "全视图预测图",
    "aim": "瞄准优化图",
}


class VisualizationPanel(ttk.Frame):
    """Header, viewport toolbar, and one resizable Matplotlib canvas."""

    def __init__(self, parent: tk.Misc, on_view_change: Callable[[str], None]) -> None:
        super().__init__(parent, style="Pane.TFrame", padding=(10, 8, 10, 8))
        self._on_view_change = on_view_change
        self._current_view = "triple"
        self._toolbar_combo_padding_y: int | None = None
        self.figures: dict[str, Figure | None] = {key: None for key in VIEW_LABELS}
        self.canvases: dict[str, FigureCanvasTkAgg | None] = {
            key: None for key in VIEW_LABELS
        }
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, style="Pane.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        self.title_var = tk.StringVar(value="Damage Field")
        self.subtitle_var = tk.StringVar(value="No prediction yet.")
        ttk.Label(header, textvariable=self.title_var, style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, textvariable=self.subtitle_var, style="PanelSubTitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(4, 2))
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(toolbar, text="视图", style="Status.TLabel").pack(side="left", padx=(0, 6))
        self.view_var = tk.StringVar(value=VIEW_LABELS[self._current_view])
        self.view_combo = ttk.Combobox(
            toolbar,
            textvariable=self.view_var,
            values=list(VIEW_LABELS.values()),
            state="readonly",
            width=16,
            style="Toolbar.TCombobox",
        )
        self.view_combo.pack(side="left")
        self.view_combo.bind("<<ComboboxSelected>>", self._handle_view_change)
        self.fit_button = ttk.Button(
            toolbar, text="适配窗口", command=self.redraw_current, style="ToolbarChinese.TButton"
        )
        self.fit_button.pack(side="left", padx=(8, 0))

        self.canvas_host = ttk.Frame(self, style="Pane.TFrame")
        self.canvas_host.grid(row=2, column=0, sticky="nsew")
        self.canvas_host.columnconfigure(0, weight=1)
        self.canvas_host.rowconfigure(0, weight=1)
        self.placeholder = ttk.Label(
            self.canvas_host,
            text="No prediction yet.",
            style="Muted.TLabel",
            anchor="center",
        )
        self.placeholder.grid(row=0, column=0, sticky="nsew")
        self._update_toolbar_state()
        self.bind("<Configure>", self._refine_toolbar_spacing, add="+")
        self.after_idle(self._refine_toolbar_spacing)

    def _refine_toolbar_spacing(self, _event: object = None) -> None:
        """Keep the selector and action button optically level at each DPI."""
        try:
            scaling = float(self.tk.call("tk", "scaling"))
        except (tk.TclError, TypeError, ValueError):
            scaling = 1.333
        if scaling < 1.85:
            padding_y = 4
        elif scaling < 2.15:
            padding_y = 6
        else:
            padding_y = 8
        if self.winfo_width() > 700 and scaling >= 1.5:
            padding_y += 2
        if padding_y == self._toolbar_combo_padding_y:
            return
        ttk.Style(self).configure("Toolbar.TCombobox", padding=(4, padding_y))
        self._toolbar_combo_padding_y = padding_y

    def _handle_view_change(self, _event: object = None) -> None:
        selected = self.view_var.get()
        key = next((key for key, label in VIEW_LABELS.items() if label == selected), "triple")
        self.set_view(key)
        self._on_view_change(key)

    def set_context(self, title: str, subtitle: str) -> None:
        self.title_var.set(title)
        self.subtitle_var.set(subtitle)

    def set_view(self, key: str) -> None:
        if key not in VIEW_LABELS:
            return
        self._current_view = key
        self.view_var.set(VIEW_LABELS[key])
        self._show_current()

    def set_figure(self, figure: Figure, key: str) -> None:
        if key not in VIEW_LABELS:
            raise KeyError(key)
        old_canvas = self.canvases.get(key)
        if old_canvas is not None:
            old_canvas.get_tk_widget().destroy()
        self.figures[key] = figure
        self.canvases[key] = None
        self._update_toolbar_state()
        if key == self._current_view:
            self._show_current()

    def clear(self, key: str) -> None:
        if key not in VIEW_LABELS:
            return
        old_canvas = self.canvases.get(key)
        if old_canvas is not None:
            old_canvas.get_tk_widget().destroy()
        self.canvases[key] = None
        self.figures[key] = None
        self._update_toolbar_state()
        if key == self._current_view:
            self._show_current()

    def _update_toolbar_state(self) -> None:
        """Keep plot-dependent controls honest before a figure exists."""
        enabled = any(figure is not None for figure in self.figures.values())
        self.view_combo.configure(state="readonly" if enabled else "disabled")
        self.fit_button.configure(state="normal" if enabled else "disabled")

    def _show_current(self) -> None:
        self.canvases[self._current_view] = None
        for child in self.canvas_host.winfo_children():
            child.destroy()
        figure = self.figures.get(self._current_view)
        if figure is None:
            self.placeholder = ttk.Label(
                self.canvas_host,
                text="No prediction yet.",
                style="Muted.TLabel",
                anchor="center",
            )
            self.placeholder.grid(row=0, column=0, sticky="nsew")
            return
        self._sync_figure_dpi(figure)
        canvas = FigureCanvasTkAgg(figure, master=self.canvas_host)
        widget = canvas.get_tk_widget()
        widget.configure(bg="#FFFFFF", highlightthickness=0, bd=0)
        widget.grid(row=0, column=0, sticky="nsew")
        canvas.draw()
        self.canvases[self._current_view] = canvas

    def _sync_figure_dpi(self, figure: Figure) -> None:
        """Render Matplotlib at monitor resolution instead of Tk bitmap scale."""
        dpi = get_window_dpi(self.winfo_toplevel())
        if dpi is None or dpi <= 0:
            return
        # Keep the existing 100-DPI baseline at 100% while increasing the
        # Agg render buffer for higher-DPI monitors. Font sizes remain in
        # points, so this changes raster quality without changing plot math.
        target_dpi = max(100, int(dpi))
        if abs(float(figure.dpi) - target_dpi) > 0.5:
            figure.set_dpi(target_dpi)

    def redraw_current(self) -> None:
        canvas = self.canvases.get(self._current_view)
        if canvas is not None:
            canvas.draw_idle()

    @property
    def current_view(self) -> str:
        return self._current_view

    @property
    def current_figure(self) -> Figure | None:
        return self.figures.get(self._current_view)
