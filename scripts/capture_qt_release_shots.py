"""Capture the curated README screenshots (Phase 2.5 §46).

Produces at 1440x900:
    11_readme_prediction_1440x900.png   (main README hero)
    12_readme_training_1440x900.png
    13_readme_validation_1440x900.png
    14_readme_registry_1440x900.png
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "qt_phase25"


def main():
    from synthetic_data import make_service, write_synthetic_dataset

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["DAMAGE_GUI_DB"] = str(OUT / "readme_shots.sqlite")
    os.environ.setdefault("DAMAGE_GUI_HOME", str(OUT / "cold_home"))

    from PySide6.QtWidgets import QApplication

    from damage_gui.model.registry import load_model, save_model
    from damage_gui.qt.main_window import DamageQtMainWindow
    from damage_gui.qt.theme import build_stylesheet

    work = OUT / "Damage Lab 测试 数据"
    model_path = work / "模型 F test.joblib"
    if not model_path.is_file():
        dataset = work / "synthetic_dataset"
        dataset.mkdir(parents=True, exist_ok=True)
        write_synthetic_dataset(dataset, velocities=(100., 200., 300.), angles=(10., 20., 30.))
        save_model(make_service(dataset).train_bundle("F"), model_path)

    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    w = DamageQtMainWindow()
    w.resize(1440, 900)
    w.show()
    w._reset_layout()

    def wait(predicate, timeout=60):
        until = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            time.sleep(0.005)
            assert time.monotonic() < until, "timeout"

    def shot(name):
        app.processEvents()
        w.grab().save(str(OUT / f"{name}.png"))

    w.translator.set_language("en")

    # Training page (populate fields via a real dataset for a credible shot)
    training = w.training_workspace
    w._navigate("training")
    training.base_config = make_service(work / "synthetic_dataset").config
    training.directory.setText(str(work / "synthetic_dataset"))
    training.inspect()
    wait(training.run_button.isEnabled)
    shot("12_readme_training_1440x900")

    # Prediction with a rendered result
    panel = w._prediction_panel
    panel._bind_bundle(load_model(model_path), str(model_path))
    panel.h_spin.setValue(2)
    panel.v_spin.setValue(200)
    panel.deg_spin.setValue(20)
    w._run_current()
    wait(lambda: not panel.is_running)
    shot("11_readme_prediction_1440x900")

    # Validation page with result
    validation = w.validation_workspace
    w._navigate("validation")
    validation.set_bundle(load_model(model_path))
    validation.mode.setCurrentIndex(validation.mode.findData("random"))
    wait(validation.run_button.isEnabled)
    w._run_current()
    wait(lambda: not w.workflow.validation.running)
    shot("13_readme_validation_1440x900")

    # Registry page
    w._navigate("models")
    w.registry_workspace.register(load_model(model_path))
    wait(lambda: w.registry_workspace.rows and not w.registry_workspace._operation)
    shot("14_readme_registry_1440x900")
    print("README screenshots captured")


if __name__ == "__main__":
    main()
