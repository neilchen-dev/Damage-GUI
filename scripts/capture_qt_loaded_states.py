"""Capture Qt Phase 1.9 states using a trained synthetic model, never fabricated metrics.

Run from the repository root with QT_QPA_PLATFORM=offscreen.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from damage_gui.data.loader import Condition
from damage_gui.model.registry import save_model
from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet
from synthetic_data import make_service, make_synthetic_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "qt_phase19")
    options = parser.parse_args()
    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    window = DamageQtMainWindow()
    window.translator.set_language("en")
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    output = options.output
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"qt_platform": app.platformName(), "captures": {}}

    def capture(name):
        app.processEvents()
        window._field_view._canvas.draw()
        app.processEvents()
        pixmap = window.grab()
        assert pixmap.save(str(output / name))
        view = window._field_view
        if view._has_result:
            import numpy as np
            buffer = np.asarray(view._canvas.buffer_rgba())
            ratio = view._canvas.device_pixel_ratio
            assert buffer.shape[1] == round(view._canvas.width() * ratio)
            assert buffer.shape[0] == round(view._canvas.height() * ratio)
            assert view.figure.dpi == view.figure._original_dpi * ratio
        evidence["captures"][name] = {
            "logical_window": [window.width(), window.height()],
            "image_pixels": [pixmap.width(), pixmap.height()],
            "device_pixel_ratio": pixmap.devicePixelRatio(),
            "canvas_dpi": view.figure.dpi,
        }

    def predict(condition):
        panel = window._prediction_panel
        for control, value in ((panel.h_spin, condition.h), (panel.v_spin, condition.v),
                               (panel.deg_spin, condition.deg)):
            control.setValue(value)
        panel._on_predict()
        deadline = time.monotonic() + 30
        while panel.is_running:
            app.processEvents()
            if time.monotonic() > deadline:
                raise TimeoutError("Prediction did not finish")
            time.sleep(0.005)
        app.processEvents()
        result = panel.current_result
        assert result is not None
        window._field_view._canvas.draw()
        return result

    capture("1440x900_no_model.png")
    tmp, directory = make_synthetic_dataset()
    try:
        trained = make_service(directory).train_bundle("F")
        # Normal inference-only export: the training files need not accompany a model.
        # The trained model, detector and metadata are retained unchanged.
        exported = dataclasses.replace(trained, data_dir="")
        with tempfile.TemporaryDirectory() as model_directory:
            model_path = str(Path(model_directory) / "synthetic_rbf.joblib")
            save_model(exported, model_path)
            QFileDialog.getOpenFileName = lambda *args, **kwargs: (model_path, "")
            window._act_open.trigger()
            app.processEvents()
            capture("1440x900_model_loaded.png")
            low = predict(Condition(2, 150, 20))
            assert low.ood_report.level == "low"
            capture("1440x900_loaded_prediction.png")
            capture("1440x900_low_confidence.png")
            axis = next(a for a in window._field_view.figure.axes if a.images)
            evidence["main_plot_width_1440"] = axis.get_window_extent().width / window._field_view._canvas.device_pixel_ratio

            evidence["low"] = {"condition": dataclasses.asdict(low.condition),
                               "confidence": low.ood_report.level,
                               "distance": low.ood_report.distance,
                               "maximum": low.peak_intensity, "area": low.damage_area_ratio,
                               "elapsed_ms": low.elapsed_ms}
            window.resize(1280, 720)
            capture("1280x720_loaded_prediction.png")
            window.translator.set_language("zh")
            capture("1280x720_loaded_prediction_zh.png")
            window.resize(1440, 900)
            capture("1440x900_low_confidence_zh.png")
            window.translator.set_language("en")
            high_condition = next(Condition(**c) for c in trained.train_conditions
                                  if trained.ood_detector.report(Condition(**c)).level == "high")
            high = predict(high_condition)
            assert high.ood_report.level == "high"
            capture("1440x900_high_confidence.png")
            evidence["high"] = {"condition": dataclasses.asdict(high.condition),
                                "confidence": high.ood_report.level,
                                "distance": high.ood_report.distance,
                                "maximum": high.peak_intensity, "area": high.damage_area_ratio,
                                "elapsed_ms": high.elapsed_ms}
            window.translator.set_language("zh")
            capture("1440x900_high_confidence_zh.png")
            window._activity.expand()
            capture("1440x900_activity_success_zh.png")
            window._activity.collapse()
            # Also exercise unchanged truth/prediction/error comparison rendering.
            window._prediction_panel._bind_bundle(trained, model_path)
            comparison = predict(high_condition)
            assert comparison.truth is not None
            capture("1440x900_comparison_zh.png")
            window.translator.set_language("en")
            capture("1440x900_comparison_en.png")
            for width, height in ((1100, 700), (1280, 720), (1600, 1000)):
                window.resize(width, height)
                capture(f"{width}x{height}_comparison_en.png")
            window.resize(1440, 900)
            capture("1440x900_comparison_en.png")
            export_path = output / "1440x900_comparison_export.png"
            window._field_view.figure.savefig(export_path, dpi=300,
                                               facecolor=window._field_view.figure.get_facecolor())
            axes = [a for a in window._field_view.figure.axes if a.images]
            evidence["comparison_prediction_width_1440"] = axes[1].get_window_extent().width / window._field_view._canvas.device_pixel_ratio
            evidence["comparison_truth_width_1440"] = axes[0].get_window_extent().width / window._field_view._canvas.device_pixel_ratio
            evidence["device_pixel_ratio"] = window._field_view._canvas.device_pixel_ratio
            evidence["display_palette"] = axes[1].images[0].get_cmap().name
            evidence["error_palette"] = axes[2].images[0].get_cmap().name

        evidence["fixture"] = "tests/synthetic_data.py: trained RBF, inference-only export"
        evidence["model_id"] = trained.metadata.model_id
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in evidence.items() if key != "captures"}, indent=2))
    finally:
        window.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()
