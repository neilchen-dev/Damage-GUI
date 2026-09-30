"""Phase 1.9 Qt workbench integration test.

Same behavior coverage as Phase 1 but against the CAE-style shell:
application bar menus, icon tool rail, dark scientific viewport,
inspector dock and collapsible activity panel.
"""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")

CODE = r'''
import os
import sys
import tempfile
import time
import numpy as np
import gc
import weakref
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QLabel

from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet

app = QApplication([])
app.setStyleSheet(build_stylesheet())
window = DamageQtMainWindow()
window.show()
app.processEvents()

def wait_prediction(panel):
    deadline = time.monotonic() + 30
    while panel.is_running:
        app.processEvents()
        assert time.monotonic() < deadline, "prediction timed out"
        time.sleep(0.005)
    app.processEvents()
    window._field_view._canvas.draw()

# 1. Empty workspace.
assert window._field_view.stack.currentIndex() == 0
assert not window._prediction_panel.predict_button.isEnabled()
assert not window._field_view._toolbar.isVisible()
assert window._act_open.shortcut().toString()
assert window._activity.is_collapsed
assert not window._act_save.isEnabled()
assert not window._act_details.isEnabled()

# Presentation invariants: no platform glyphs and no light empty canvas.
from PySide6.QtGui import QPalette
assert window._field_view.stack.widget(0).palette().color(QPalette.Window).name() == "#15191f"
assert all(not button.icon().isNull() for button, _ in window.rail._buttons.values())
assert all(not button.icon().isNull() for button in window._field_view.buttons.values())
assert window._prediction_panel.h_spin.height() == 34
assert window._prediction_panel.predict_button.height() == 36

# 2. Load a real model trained from synthetic data.
sys.path.insert(0, "tests")
from synthetic_data import make_synthetic_dataset, make_service
from damage_gui.model.registry import save_model

tmp, directory = make_synthetic_dataset()
bundle = make_service(directory).train_bundle("F")
with tempfile.TemporaryDirectory() as model_dir:
    model_path = str(Path(model_dir) / "model.joblib")
    save_model(bundle, model_path)
    QFileDialog.getOpenFileName = lambda *a, **k: (model_path, "")
    window._act_open.trigger()
    app.processEvents()
    panel = window._prediction_panel
    assert panel.bundle.level == "F"
    assert window._act_save.isEnabled()
    assert window._act_details.isEnabled()
    assert panel.model_values["type"].text() == "RBF"
    assert panel.model_values["level"].text() == "F"
    assert len(panel.model_values["id"].text()) >= 8

    assert not window._field_view.load_button.isVisible()
    assert "ready" in window._field_view.empty_title.text().lower() or "就绪" in window._field_view.empty_title.text()
    assert all(not button.isEnabled() for button in window._field_view.buttons.values())
    assert panel.predict_button.isEnabled()
    assert window._act_run.isEnabled()
    assert not window._act_export.isEnabled()

    # 3. Predict and verify the dark scientific viewport.
    panel.h_spin.setValue(2)
    window._act_run.trigger()
    wait_prediction(panel)
    result = panel.current_result
    assert result is not None
    assert panel.result_values["maximum"].text() == f"{result.peak_intensity:.3f}"
    assert panel.result_values["area"].text() == f"{result.damage_area_ratio:.1%}"
    assert window._field_view.figure.canvas is window._field_view._canvas
    assert window._field_view.stack.currentIndex() == 1
    view = window._field_view
    assert view._canvas.device_pixel_ratio == float(os.environ["QT_SCALE_FACTOR"])
    assert view.figure.dpi == view.figure._original_dpi * view._canvas.device_pixel_ratio
    pixels = np.asarray(view._canvas.buffer_rgba())
    assert pixels.shape[1] == round(view._canvas.width() * view._canvas.device_pixel_ratio)
    assert pixels.shape[0] == round(view._canvas.height() * view._canvas.device_pixel_ratio)
    face = window._field_view.figure.patch.get_facecolor()
    assert abs(face[0] - 0x15 / 255) < 1e-3
    assert abs(face[1] - 0x19 / 255) < 1e-3
    assert abs(face[2] - 0x1F / 255) < 1e-3
    for axis in window._field_view.figure.axes:
        assert axis.get_facecolor()[:3] == (0x15 / 255, 0x19 / 255, 0x1F / 255)

    # 4. Viewport tools keep matplotlib mode in sync.
    window._field_view.buttons["Pan"].click()
    assert window._field_view.buttons["Pan"].isChecked()
    assert window._act_pan.isChecked()
    window._field_view.buttons["Zoom"].click()
    assert not window._field_view.buttons["Pan"].isChecked()
    assert window._field_view.buttons["Zoom"].isChecked()
    window._field_view.buttons["Probe"].click()
    assert window._field_view.buttons["Probe"].isChecked()
    window._field_view.buttons["Probe"].click()
    assert not window._field_view.buttons["Probe"].isChecked()

    # 5. New prediction resets navigation mode.
    panel._on_predict()
    wait_prediction(panel)
    assert not window._field_view.buttons["Zoom"].isChecked()

    # Twenty actual predictions: stable axes/widget counts and collectible old figures.
    old_figures = []
    axes_count = len(window._field_view.figure.axes)
    widget_count = len(panel.findChildren(QLabel))
    started = time.monotonic()
    for _ in range(20):
        old_figures.append(weakref.ref(window._field_view.figure))
        previous = window._field_view.figure
        panel._on_predict()
        assert panel.is_running
        assert not panel.predict_button.isEnabled()
        assert window._field_view.figure is previous
        assert all(not button.isEnabled() for button in window._field_view.buttons.values())
        worker = panel._worker
        panel._on_predict()
        assert panel._worker is worker  # repeated submit is ignored
        wait_prediction(panel)
        assert len(window._field_view.figure.axes) == axes_count
        assert len(panel.findChildren(QLabel)) == widget_count
    del previous, worker
    gc.collect()
    assert all(ref() is None for ref in old_figures)
    assert time.monotonic() - started < 30

    # Recoverable error keeps previous result, records traceback, never shows a modal.
    service = panel.prediction_service
    previous = window._field_view.figure
    class FailingService:
        def predict(self, *args, **kwargs):
            raise RuntimeError("internal test detail")
    panel.prediction_service = FailingService()
    panel._on_predict()
    wait_prediction(panel)
    assert window._field_view.figure is previous
    assert panel.predict_button.isEnabled()
    assert "Traceback" in window._activity.logs.toPlainText()
    assert "internal test detail" not in window._activity.status.text()
    panel.prediction_service = service
    panel._on_predict()
    wait_prediction(panel)
    assert not window._field_view._failed

    # Figure export defaults to an actual 300 DPI PNG.
    from PIL import Image
    with tempfile.TemporaryDirectory() as export_dir:
        export_path = str(Path(export_dir) / "prediction.png")
        QFileDialog.getSaveFileName = lambda *a, **k: (export_path, "")
        window._field_view.buttons["Export"].click()
        with Image.open(export_path) as exported:
            assert abs(exported.info["dpi"][0] - 300) < 1
        assert window._field_view.figure.canvas is window._field_view._canvas

    # 6. Save the model back to disk.
    with tempfile.TemporaryDirectory() as out_dir:
        out_path = str(Path(out_dir) / "copy.joblib")
        QFileDialog.getSaveFileName = lambda *a, **k: (out_path, "")
        window._act_save.trigger()
        assert Path(out_path).exists()

    image = next(axis.images[0] for axis in window._field_view.figure.axes if axis.images)
    import numpy as np
    original_array = image.get_array().copy()
    original_clim, original_cmap = image.get_clim(), image.get_cmap().name

    # 7. Bilingual layout at three sizes; inspector inputs stay in bounds.
    for language in ("zh", "en"):
        window.translator.set_language(language)
        for width, height in ((1440, 900), (1280, 720), (1100, 700), (1600, 1000)):
            window.resize(width, height)
            app.processEvents()
            window._field_view._canvas.draw()
            title = next(axis for axis in window._field_view.figure.axes if axis.images).get_title()
            assert title == ("预测毁伤场" if language == "zh" else "Predicted Damage Field")
            assert np.array_equal(image.get_array(), original_array)
            assert image.get_clim() == original_clim
            assert image.get_cmap().name == original_cmap
            for widget in (panel.level_combo, panel.h_spin, panel.v_spin, panel.deg_spin,
                           panel.predict_button):
                assert widget.geometry().bottom() < panel.height()
                assert widget.geometry().right() < panel.width()
            assert window.rail.width() <= 60
            assert 260 <= window.inspector.width() <= 300

    # Real truth comparison: retain all scientific arrays, cmap and limits,
    # while making the prediction larger than either comparison plot.
    from damage_gui.data.loader import Condition
    from damage_gui.visualization.plots import render_heatmaps
    condition = next(Condition(**c) for c in bundle.train_conditions
                     if bundle.ood_detector.report(Condition(**c)).level == "high")
    for control, value in ((panel.h_spin, condition.h), (panel.v_spin, condition.v),
                           (panel.deg_spin, condition.deg)):
        control.setValue(value)
    panel._on_predict()
    wait_prediction(panel)
    comparison = panel.current_result
    assert comparison.truth is not None
    comparison_refs = []
    for _ in range(20):
        comparison_refs.append(weakref.ref(window._field_view.figure))
        panel._on_predict()
        wait_prediction(panel)
        assert len(window._field_view.figure.axes) == 6
    gc.collect()
    assert all(ref() is None for ref in comparison_refs)
    # Reusing a Figure on a Retina canvas must not multiply its DPI a second time.
    view = window._field_view
    dpi = view.figure.dpi
    view.show_figure(view.figure)
    view._canvas.draw()
    assert view.figure.dpi == dpi
    reference = render_heatmaps(comparison.truth, comparison.prediction,
                                bundle.resolved_config().display_threshold,
                                config=bundle.resolved_config())
    expected = [(axis.images[0].get_array().copy(), axis.images[0].get_clim(),
                 axis.images[0].get_cmap().name) for axis in reference.axes if axis.images]
    for language in ("zh", "en"):
        window.translator.set_language(language)
        for size in ((1440, 900), (1280, 720), (1100, 700), (1600, 1000)):
            window.resize(*size)
            app.processEvents()
            window._field_view._canvas.draw()
            axes = [axis for axis in window._field_view.figure.axes if axis.images]
            assert len(window._field_view.figure.axes) == 6
            assert axes[0].get_window_extent().width >= 160
            for axis in axes:
                image_box = axis.get_window_extent()
                colorbar_box = axis.images[0].colorbar.ax.get_window_extent()
                assert abs(colorbar_box.y0 - image_box.y0) < 1
                assert abs(colorbar_box.height - image_box.height) < 1
                ratio = window._field_view._canvas.device_pixel_ratio
                assert 6 <= colorbar_box.width / ratio <= 10
                assert 5 <= (colorbar_box.x0 - image_box.x1) / ratio <= 12
                x0, x1, y0, y1 = axis.images[0].get_extent()
                assert abs(image_box.width / image_box.height - abs((x1-x0)/(y1-y0))) < 0.01
            assert axes[1].get_window_extent().width > axes[0].get_window_extent().width * 1.3
            for axis, (array, limits, cmap) in zip(axes, expected):
                assert np.array_equal(axis.images[0].get_array(), array)
                assert axis.images[0].get_clim() == limits
                assert axis.images[0].get_cmap().name == ("error_dark_coolwarm" if axis is axes[2] else "damage_dark_cividis")
            assert axes[1].get_title() == ("预测毁伤场" if language == "zh" else "Predicted Damage Field")
    reference.clear()

    # 8. Tool rail navigation and inspector switching.
    for key, page in window._pages.items():
        window._navigate(key)
        app.processEvents()
        assert window.pages.currentWidget() is page
        expected = {"prediction": 0, "batch": 2, "history": 3, "validation": 4, "training": 5, "models": 6}.get(key, 1)
        assert window.inspector.currentIndex() == expected
    window._navigate("prediction")
    assert window.inspector.currentWidget() is panel

    # 9. Activity panel expand/collapse.
    window._activity.collapse()
    app.processEvents()
    assert window._activity.height() <= 36
    assert abs(sum(window.splitter.sizes()) + window.splitter.handleWidth() - window.splitter.height()) <= 2
    window._activity.expand()
    app.processEvents()
    assert window._activity.height() >= 120
    window._activity.collapse()
    assert window._activity.is_collapsed

    # Repeated tab click collapses; a different tab switches without collapsing.
    activity = window._activity
    activity._tabs["jobs"].click()
    app.processEvents()
    assert not activity.is_collapsed
    assert 180 <= activity.height() <= 220
    activity._tabs["logs"].click()
    assert not activity.is_collapsed
    assert activity.stack.currentWidget() is activity.logs
    activity._tabs["logs"].click()
    app.processEvents()
    assert activity.is_collapsed
    assert activity.height() == 34

    # 10. Reloading a model clears previous results.
    window._act_open.trigger()
    app.processEvents()
    assert panel.current_result is None
    assert window._field_view.stack.currentIndex() == 0
    assert panel.result_values["maximum"].text() == "—"
    assert window._act_save.isEnabled()
    assert not window._field_view.buttons["Pan"].isEnabled()
    assert not window._act_export.isEnabled()
    assert window._act_run.isEnabled()
    assert not panel.result_values["confidence"].toolTip()
    panel.prediction_service = FailingService()
    panel._on_predict()
    assert window._field_view.empty_title.text() in ("Predicting…", "Running prediction…", "正在运行预测…")
    wait_prediction(panel)
    assert window._field_view.empty_title.text() in ("Prediction failed", "预测失败")
    assert window._field_view.stack.currentIndex() == 0
    assert panel.predict_button.isEnabled()
    # A close request during computation completes safely, then closes the window.
    panel._on_predict()
    window.close()
    assert window.isVisible()
    wait_prediction(panel)
    app.processEvents()
    assert not window.isVisible()

window.close()
tmp.cleanup()
print("OK")
'''


@pytest.mark.parametrize("scale", ("1", "2"))
def test_qt_workbench(scale, tmp_path):
    command = [sys.executable, "-c", CODE]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale, "DAMAGE_GUI_DB": str(tmp_path / "trace.sqlite")})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
