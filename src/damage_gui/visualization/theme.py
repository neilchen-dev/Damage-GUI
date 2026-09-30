"""Pure Python scientific display tokens shared by Qt and headless Matplotlib.

No Qt imports, backend selection, global rcParams, or numerical configuration.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScientificTheme:
    background: str = "#15191F"
    edge: str = "#56606D"
    tick: str = "#9FA9B7"
    label: str = "#C7CFDA"
    title: str = "#DCE2EA"
    grid: str = "#2A313A"
    error_cool: str = "#5B9FC9"
    error_warm: str = "#D87962"
    title_size: float = 8.5  # Matplotlib points; ~12 logical pixels at 100 dpi.
    label_size: float = 8.0
    tick_size: float = 7.5
    colorbar_width: float = 0.075  # Inches; DPI scaling is handled by the canvas.
    colorbar_gap: float = 0.08


DARK_SCIENTIFIC = ScientificTheme()
