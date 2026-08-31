"""GUI 通用小部件工具：圆角矩形绘制、自适应换行标签。"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import Any


def rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs,
) -> int:
    """在 Canvas 上绘制圆角矩形（smooth polygon 近似）。"""
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def bind_autowrap(label: tk.Label, min_width: int = 80) -> None:
    """让 Label 的换行宽度跟随实际可用宽度，避免固定 wraplength 截断长文本。"""

    def on_configure(event: tk.Event[tk.Label]) -> None:
        label.configure(wraplength=max(event.width - 8, min_width))

    label.bind("<Configure>", on_configure)


def compact_path(path: str | Path, max_chars: int = 42) -> str:
    """Keep a displayed path compact while retaining its useful tail."""
    text = str(path)
    if len(text) <= max_chars:
        return text
    separator = "\\" if "\\" in text else "/"
    parts = [part for part in text.replace("/", "\\").split("\\") if part]
    tail = separator.join(parts[-2:]) if len(parts) >= 2 else text
    candidate = f"…{separator}{tail}"
    if len(candidate) <= max_chars:
        return candidate
    return f"…{text[-(max_chars - 1):]}"


def bind_tooltip(
    widget: tk.Misc,
    text: str | Callable[[], str],
    *,
    delay_ms: int = 500,
) -> None:
    """Show optional long-form context without expanding the workbench panes."""
    state: dict[str, Any] = {"after_id": None, "window": None}

    def resolve_text() -> str:
        value = text() if callable(text) else text
        return str(value).strip()

    def hide(_event: object = None) -> None:
        after_id = state.pop("after_id", None)
        if after_id is not None:
            try:
                widget.after_cancel(after_id)
            except tk.TclError:
                pass
        tooltip = state.pop("window", None)
        if tooltip is not None:
            try:
                tooltip.destroy()
            except tk.TclError:
                pass

    def show() -> None:
        state["after_id"] = None
        try:
            if not widget.winfo_exists():
                return
            value = resolve_text()
            if not value:
                return
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.transient(widget.winfo_toplevel())
            label = tk.Label(
                tooltip,
                text=value,
                justify="left",
                anchor="w",
                wraplength=600,
                background="#FFFFE1",
                foreground="#1F2933",
                relief="solid",
                borderwidth=1,
                padx=6,
                pady=3,
                font=("Segoe UI", 9),
            )
            label.pack()
            tooltip.update_idletasks()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 3
            tooltip.geometry(f"+{x}+{y}")
            state["window"] = tooltip
        except tk.TclError:
            return

    def schedule(_event: object = None) -> None:
        hide()
        state["after_id"] = widget.after(delay_ms, show)

    widget.bind("<Enter>", schedule, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<ButtonPress>", hide, add="+")
