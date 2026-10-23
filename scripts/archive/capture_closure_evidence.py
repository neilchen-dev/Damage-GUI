"""为结题报告采集「实际程序运行效果」截图：真实部署模型 + 主追溯库。

Run:  .venv/bin/python scripts/capture_closure_evidence.py
输出: outputs/closure_report/run_evidence/
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "closure_report" / "run_evidence"
MODEL_DIR = ROOT / "outputs" / "deploy_models"
BATCH_CSV = OUT / "batch_conditions_F.csv"


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["DAMAGE_GUI_DB"] = str(ROOT / "damage_gui.db")

    from PySide6.QtWidgets import QApplication

    from damage_gui.model.registry import load_model
    from damage_gui.qt.main_window import DamageQtMainWindow
    from damage_gui.qt.theme import build_stylesheet

    OUT.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    w = DamageQtMainWindow()
    w.resize(1440, 900)
    w.show()
    w.translator.set_language("zh")
    app.processEvents()

    def wait(predicate, timeout=120):
        until = time.monotonic() + timeout
        while not predicate():
            app.processEvents()
            time.sleep(0.01)
            assert time.monotonic() < until, "timeout"

    def shot(name):
        app.processEvents()
        try:
            w._field_view._canvas.draw()
        except Exception:
            pass
        app.processEvents()
        assert w.grab().save(str(OUT / name)), f"save failed: {name}"
        print("captured", name)

    # ---- 1. 预测页：载入真实 F 级部署模型并预测 ----
    model_path = MODEL_DIR / "damagelab_pod_rbf_F.joblib"
    panel = w._prediction_panel
    panel._bind_bundle(load_model(model_path), str(model_path))
    app.processEvents()
    panel.h_spin.setValue(2)
    panel.v_spin.setValue(200)
    panel.deg_spin.setValue(20)
    panel._on_predict()
    wait(lambda: not panel.is_running)
    app.processEvents()
    shot("01_prediction_real.png")

    # ---- 2. 批量页：真实模型 + 工况 CSV 全流程 ----
    w._navigate("batch")
    bw = w.batch_workspace
    bw.csv_edit.setText(str(BATCH_CSV))
    app.processEvents()
    bw.validate()
    wait(lambda: bw.parsed is not None, 60)
    app.processEvents()
    bw.run()
    wait(lambda: w.workflow.report is not None, 180)
    app.processEvents()
    shot("02_batch_real.png")

    # ---- 3. 历史页：主追溯库中的真实任务记录 ----
    w._navigate("history")
    app.processEvents()
    wait(lambda: w.history_workspace.model.rowCount() > 0, 30)
    app.processEvents()
    shot("03_history_real.png")

    # ---- 4. 模型库页 ----
    w._navigate("models")
    app.processEvents()
    shot("04_models_real.png")

    # 收尾：排空后台任务，避免模态框挂起
    deadline = time.monotonic() + 10
    while w.task_adapter.is_busy() or w.workflow._requests:
        app.processEvents()
        if time.monotonic() > deadline:
            break
        time.sleep(0.005)
    w.close()
    print("done")


if __name__ == "__main__":
    main()
