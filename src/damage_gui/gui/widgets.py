"""GUI 通用小部件工具：圆角矩形绘制、自适应换行标签。"""
from __future__ import annotations

import tkinter as tk


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

    def on_configure(event: "tk.Event[tk.Label]") -> None:
        label.configure(wraplength=max(event.width - 8, min_width))

    label.bind("<Configure>", on_configure)
