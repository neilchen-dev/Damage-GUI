"""Opt-in dark viewport styling; arrays, extents and Normalize objects stay intact.

Legacy renderers retain their original appearance. The viewport palette is a
cividis-derived sequential map: the lowest 8% of its RGB ramp is smoothly blended
from the viewport background. No values are masked, thresholded or renormalized.
The error ramp has a dark zero and cool negative / warm positive endpoints.
"""
from functools import lru_cache

import matplotlib
import numpy as np
from matplotlib import colors, ticker
from matplotlib.transforms import Bbox

from damage_gui.visualization.theme import DARK_SCIENTIFIC

_LABELS = {
    "zh": ("真实毁伤场", "预测毁伤场", "误差（预测 − 真实）", "毁伤强度", "误差"),
    "en": ("Ground Truth", "Predicted Damage Field", "Error (Prediction − Truth)",
           "Damage Intensity", "Error"),
}


@lru_cache(maxsize=1)
def _display_colormaps():
    theme = DARK_SCIENTIFIC
    values = np.linspace(0, 1, 256)
    rgba = matplotlib.colormaps["cividis"](values)
    background = np.array(colors.to_rgb(theme.background))
    blend = np.minimum(values / 0.08, 1)[:, None]
    rgba[:, :3] = background * (1 - blend) + rgba[:, :3] * blend
    damage = colors.ListedColormap(rgba, name="damage_dark_cividis")
    damage = damage.with_extremes(bad=theme.background, under=theme.background)
    error = colors.LinearSegmentedColormap.from_list(
        "error_dark_coolwarm", [theme.error_cool, theme.background, theme.error_warm], N=257,
    )
    error = error.with_extremes(bad=theme.background)
    return damage, error


class _ColorbarLocator:
    """Place a constant logical-width bar beside the actual equal-aspect plot.

    Relative subplot cells can leave the bar far from a letterboxed image.
    Using the drawn parent position also keeps the height aligned during resize
    and savefig, without a callback or a fixed canvas DPI.
    """
    def __init__(self, parent):
        self.parent = parent

    def __call__(self, axis, renderer):
        theme = DARK_SCIENTIFIC
        box = self.parent.get_position()
        width = axis.figure.get_size_inches()[0]
        return Bbox.from_bounds(box.x1 + theme.colorbar_gap / width, box.y0,
                                theme.colorbar_width / width, box.height)


def _layout_fields(figure, axes):
    """Reserve readable comparison plots; do not change the application layout."""
    figure.set_layout_engine(None)
    if len(axes) == 1:
        grid = figure.add_gridspec(1, 1, left=0.08, right=0.90, bottom=0.07, top=0.95)
        positions = ((axes[0], grid[0, 0]),)
    elif len(axes) == 3:
        truth, prediction, error = axes
        grid = figure.add_gridspec(2, 2, width_ratios=(1.7, 1),
                                  left=0.075, right=0.90, bottom=0.075, top=0.95,
                                  wspace=0.32, hspace=0.32)
        positions = ((prediction, grid[:, 0]), (truth, grid[0, 1]), (error, grid[1, 1]))
    else:
        return
    for axis, cell in positions:
        axis.set_subplotspec(cell)
        axis.set_anchor("C")
        axis.yaxis.set_visible(True)
        axis.set_ylabel("y (m)")
        colorbar = axis.images[0].colorbar
        if colorbar is not None:
            # This locator provides the reserved bar position. Disable the original
            # renderer's automatic bar placement without recreating any artists.
            colorbar.ax.set_in_layout(False)
            colorbar.ax.set_box_aspect(None)
            colorbar.ax.set_aspect("auto")
            colorbar.ax.set_axes_locator(_ColorbarLocator(axis))


def translate_scientific_figure(figure, language="en"):
    """Translate titles/legends on the existing figure, without another prediction."""
    if language not in _LABELS:
        raise ValueError(f"Unsupported scientific plot language: {language}")
    theme = DARK_SCIENTIFIC
    truth, prediction, error, intensity, error_label = _LABELS[language]
    axes = [axis for axis in figure.axes if axis.images]
    titles = (prediction,) if len(axes) == 1 else (truth, prediction, error)
    for index, (axis, title) in enumerate(zip(axes, titles, strict=False)):
        axis.set_title(title, fontsize=theme.title_size,
                       color=theme.tick if len(axes) == 1 else theme.title, pad=6)
        colorbar = axis.images[0].colorbar
        if colorbar is not None:
            is_error = len(axes) == 3 and index == 2
            colorbar.set_label(error_label if is_error else intensity,
                               fontsize=theme.label_size, color=theme.label, labelpad=5)
            low, high = axis.images[0].get_clim()
            colorbar.set_ticks(np.linspace(low, high, 5))
            formatter = (ticker.FuncFormatter(
                lambda value, _: "0%" if abs(value) < 1e-12 else f"{value * 100:+.0f}%"
            ) if is_error else ticker.PercentFormatter(xmax=1, decimals=0))
            colorbar.ax.yaxis.set_major_formatter(formatter)


def apply_scientific_theme(figure, language="en"):
    """Apply the viewport theme in place and return the same Figure.

    Idempotent: layout/locators are assigned once, no axes or colorbars are added.
    Prediction and truth use identical display colors and the original 0–1 norm;
    signed error keeps the original renderer's symmetric limits and data.
    """
    theme = DARK_SCIENTIFIC
    figure.patch.set_facecolor(theme.background)
    axes = [axis for axis in figure.axes if axis.images]
    damage, error = _display_colormaps()
    for index, axis in enumerate(axes):
        is_error = len(axes) == 3 and index == 2
        axis.images[0].set_cmap((error if is_error else damage).copy())
    if not getattr(figure, "_damage_dark_layout", False):
        _layout_fields(figure, axes)
        figure._damage_dark_layout = True
    for axis in figure.axes:
        axis.set_facecolor(theme.background)
        axis.tick_params(colors=theme.tick, labelsize=theme.tick_size, length=2, width=0.5)
        axis.xaxis.label.set(color=theme.label, fontsize=theme.label_size)
        axis.yaxis.label.set(color=theme.label, fontsize=theme.label_size)
        axis.xaxis.get_offset_text().set_color(theme.tick)
        axis.yaxis.get_offset_text().set_color(theme.tick)
        for spine in axis.spines.values():
            spine.set_color(theme.edge)
            spine.set_linewidth(0.6)
            spine.set_alpha(0.65)
        for line in (*axis.get_xgridlines(), *axis.get_ygridlines()):
            line.set_color(theme.grid)
            line.set_alpha(0.2)
        for text in axis.texts:
            text.set_color(theme.label)
    # The legacy signed-error colorbar marks zero with a dark line; use the same
    # muted tick color so the marker remains legible on the new dark neutral.
    for axis in axes:
        colorbar = axis.images[0].colorbar
        if colorbar is not None:
            colorbar.outline.set_visible(False)
            for line in colorbar.ax.lines:
                line.set_color(theme.tick)
                line.set_linewidth(0.6)
    if figure._suptitle is not None:
        figure._suptitle.set_color(theme.title)
    translate_scientific_figure(figure, language)
    return figure
