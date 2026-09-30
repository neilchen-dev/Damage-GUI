"""Opt-in viewport colors must not alter numerical fields or legacy rendering."""
import gc
import importlib.util
import os
import subprocess
import sys
import weakref

import matplotlib
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgba

from damage_gui.config import DAMAGE_CMAP, ERROR_CMAP
from damage_gui.visualization.plots import render_heatmaps
from damage_gui.visualization.scientific_theme import (
    apply_scientific_theme,
    translate_scientific_figure,
)
from damage_gui.visualization.theme import DARK_SCIENTIFIC


@pytest.fixture
def fields():
    y, x = np.mgrid[-1:1:32j, -1:1:48j]
    truth = 0.7 * np.exp(-5 * (x*x + y*y))
    prediction = 0.6 * np.exp(-5 * ((x - 0.2)**2 + y*y))
    return truth, prediction


def images(figure):
    return [axis.images[0] for axis in figure.axes if axis.images]


def test_dark_theme_preserves_fields_and_default_frontends(fields):
    truth, prediction = fields
    original_truth, original_prediction = truth.copy(), prediction.copy()
    legacy = render_heatmaps(truth, prediction, 0.08)
    before = [(im.get_array().copy(), im.get_extent(), im.norm, im.get_clim())
              for im in images(legacy)]
    assert [im.get_cmap().name for im in images(legacy)] == [DAMAGE_CMAP, DAMAGE_CMAP, ERROR_CMAP]
    assert apply_scientific_theme(legacy, "en") is legacy
    for im, (array, extent, norm, limits) in zip(images(legacy), before, strict=False):
        assert np.array_equal(im.get_array(), array)
        assert not np.any(np.ma.getmaskarray(im.get_array()))
        assert im.get_extent() == extent
        assert im.norm is norm
        assert im.get_clim() == limits
    assert np.array_equal(truth, original_truth)
    assert np.array_equal(prediction, original_prediction)
    ims = images(legacy)
    assert ims[0].get_clim() == ims[1].get_clim() == (0, 1)
    points = np.linspace(0, 1, 257)
    assert np.array_equal(ims[0].get_cmap()(points), ims[1].get_cmap()(points))
    assert ims[2].get_clim()[0] == -ims[2].get_clim()[1]
    assert np.allclose(ims[2].get_cmap()(0.5), to_rgba(DARK_SCIENTIFIC.background))
    assert ims[0].get_cmap()(0.0) == to_rgba(DARK_SCIENTIFIC.background)
    # Brightness grows with magnitude: grayscale cannot reverse low/high severity.
    rgb = ims[0].get_cmap()(np.linspace(0, 1, 256))[:, :3]
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055)/1.055)**2.4)
    luminance = linear @ np.array([0.2126, 0.7152, 0.0722])
    assert np.all(np.diff(luminance) >= -1e-6)
    assert luminance[-1] > luminance[0] * 20
    # Global registered maps and default renderer remain untouched after dark use.
    default = render_heatmaps(truth, prediction, 0.08)
    assert [im.get_cmap().name for im in images(default)] == [DAMAGE_CMAP, DAMAGE_CMAP, ERROR_CMAP]
    assert matplotlib.colormaps[DAMAGE_CMAP](0.0) != to_rgba(DARK_SCIENTIFIC.background)
    legacy.clear()
    default.clear()


def test_theme_layout_export_and_i18n(fields, tmp_path):
    truth, prediction = fields
    figure = render_heatmaps(truth, prediction, 0.08, theme="dark", language="en")
    canvas = FigureCanvasAgg(figure)
    axes_count = len(figure.axes)
    for language in ("zh", "en"):
        translate_scientific_figure(figure, language)
        for size in ((7.64, 5.5), (9.44, 5.5), (11.04, 7.3), (12.64, 8.3)):
            figure.set_size_inches(*size)
            apply_scientific_theme(figure, language)
            canvas.draw()
            assert len(figure.axes) == axes_count == 6
            for im in images(figure):
                box = im.axes.get_window_extent()
                bar = im.colorbar.ax.get_window_extent()
                assert abs(box.y0-bar.y0) < 0.01
                assert abs(box.height-bar.height) < 0.01
                assert abs(bar.width - DARK_SCIENTIFIC.colorbar_width * figure.dpi) < 0.01
                assert abs(bar.x0-box.x1 - DARK_SCIENTIFIC.colorbar_gap * figure.dpi) < 0.01
                assert len(im.colorbar.get_ticks()) == 5
                for axis in (im.axes, im.colorbar.ax):
                    extent = axis.get_tightbbox(canvas.get_renderer())
                    assert extent.x0 >= 0 and extent.y0 >= 0
                    assert extent.x1 <= figure.bbox.width and extent.y1 <= figure.bbox.height
                # The colormap changes display colors, never geometric aspect.
                x0, x1, y0, y1 = im.get_extent()
                assert abs(box.width/box.height - abs((x1-x0)/(y1-y0))) < 0.001
    export = tmp_path / "dark.png"
    figure.savefig(export, dpi=300, facecolor=figure.get_facecolor())
    from PIL import Image
    with Image.open(export) as png:
        assert abs(png.info["dpi"][0] - 300) < 1
        assert png.convert("RGB").getpixel((0, 0)) == (21, 25, 31)
    figure.clear()


def test_repeated_dark_render_is_collectible(fields):
    refs = []
    for _ in range(20):
        figure = render_heatmaps(*fields, 0.08, theme="dark", language="en")
        canvas = FigureCanvasAgg(figure)
        canvas.draw()
        assert len(figure.axes) == 6
        refs.append(weakref.ref(figure))
    del figure, canvas
    gc.collect()
    assert all(ref() is None for ref in refs)


def test_scientific_theme_stays_headless():
    code = r'''
import sys
from importlib.abc import MetaPathFinder
class BlockQt(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("PySide6", "damage_gui.qt", "tkinter")):
            raise ImportError(fullname)
sys.meta_path.insert(0, BlockQt())
import numpy as np
from damage_gui.visualization.plots import render_heatmaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
figure = render_heatmaps(None, np.zeros((32, 48)), 0.08, theme="dark", language="en")
FigureCanvasAgg(figure).draw()
assert not any(name.startswith(("PySide6", "damage_gui.qt", "tkinter")) for name in sys.modules)
import damage_gui.cli
import damage_gui.webapp.app
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={**os.environ, "MPLBACKEND": "Agg"}, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_legacy_tk_import_without_a_window():
    if importlib.util.find_spec("tkinter") is None or importlib.util.find_spec("_tkinter") is None:
        pytest.skip("Tkinter unavailable in this Python build")
    result = subprocess.run([sys.executable, "-c", "import damage_gui.gui.main_window"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
