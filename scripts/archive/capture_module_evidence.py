"""为结题报告采集「各功能模块实际运行效果」截图（全部真实运行）。

模式:
  main     — 主追溯库（damage_gui.db）：预测 / 验证 / 训练 / 批量 / 历史
  registry — 演示注册库：注册 F/M/P 三个部署模型后截模型库页

Run:
  .venv/bin/python scripts/capture_module_evidence.py main
  .venv/bin/python scripts/capture_module_evidence.py registry
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "closure_report" / "run_evidence"
MODEL_DIR = ROOT / "outputs" / "deploy_models"
DATA_DIR = Path.home() / "Downloads" / "003" / "data"
BATCH_CSV = OUT / "batch_conditions_F.csv"


def make_app(db_path: Path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["DAMAGE_GUI_DB"] = str(db_path)

    from PySide6.QtWidgets import QApplication

    from damage_gui.qt.main_window import DamageQtMainWindow
    from damage_gui.qt.theme import build_stylesheet

    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    w = DamageQtMainWindow()
    w.resize(1440, 900)
    w.show()
    w.translator.set_language("zh")
    app.processEvents()
    return app, w


def wait(app, predicate, timeout=900, what=""):
    until = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        time.sleep(0.02)
        assert time.monotonic() < until, f"timeout: {what}"


def shot(app, w, name, canvases=()):
    app.processEvents()
    for c in canvases:
        try:
            c.draw()
        except Exception:
            pass
    app.processEvents()
    assert w.grab().save(str(OUT / name)), f"save failed: {name}"
    print("captured", name)


def drain(app, w):
    deadline = time.monotonic() + 10
    while (w.task_adapter.is_busy() or w.workflow._requests) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def main_mode():
    app, w = make_app(ROOT / "damage_gui.db")

    from damage_gui.model.registry import load_model

    model_path = MODEL_DIR / "damagelab_pod_rbf_F.joblib"
    panel = w._prediction_panel
    panel._bind_bundle(load_model(model_path), str(model_path))
    app.processEvents()

    # ---- 1. 预测页：真实 F 级部署模型 + 单工况预测 ----
    panel.h_spin.setValue(2)
    panel.v_spin.setValue(200)
    panel.deg_spin.setValue(20)
    panel._on_predict()
    wait(app, lambda: not panel.is_running, 120, "prediction")
    app.processEvents()
    shot(app, w, "01_prediction_real.png", (w._field_view._canvas,))

    # ---- 2. 验证页：真实模型 + 真实数据集，随机留出全流程 ----
    w._navigate("validation")
    vw = w.validation_workspace
    vw.data_edit.setText(str(DATA_DIR))
    vw._discover()
    wait(app, lambda: bool(getattr(vw, "records", [])), 300, "validation discover")
    wait(app, lambda: vw.compatible, 120, "validation compatibility")
    app.processEvents()
    vw.run()
    wait(app, lambda: vw.result is not None or (
        vw.controller.job and vw.controller.job["status"] in ("FAILED", "CANCELLED")),
         600, "validation run")
    assert vw.result is not None, "validation failed"
    app.processEvents()
    shot(app, w, "05_validation_overview.png")

    # 样本对比：选 P95HybridError 最差的样本展示真值 vs 预测
    rows = vw.sample_model.rows
    worst = max(range(len(rows)),
                key=lambda i: rows[i].get("P95HybridError (%)") or -1)
    vw.open_sample(vw.sample_model.index(worst, 0))
    app.processEvents()
    shot(app, w, "06_validation_comparison.png", (vw.comparison._canvas,))

    # ---- 3. 训练页：真实数据集 F 级 POD-RBF(K=20) 完整训练 ----
    w._navigate("training")
    tw = w.training_workspace
    tw.directory.setText(str(DATA_DIR))
    tw.inspect()
    wait(app, lambda: tw.dataset is not None, 600, "dataset inspection")
    app.processEvents()
    tw.level.setCurrentText("F")
    tw.model_type.setCurrentIndex(1)  # POD-RBF
    tw.components.setValue(20)
    app.processEvents()
    tw.run()
    wait(app, lambda: tw.result is not None or (
        tw.training.job and tw.training.job["status"] in ("FAILED", "CANCELLED")),
         900, "training run")
    assert tw.result is not None, "training failed"
    app.processEvents()
    shot(app, w, "07_training_summary.png")
    tw.tabs.setCurrentIndex(2)  # POD 谱图
    app.processEvents()
    tw.canvas.draw_idle()
    shot(app, w, "08_training_spectrum.png", (tw.canvas,))

    # ---- 4. 批量页：真实模型 + 工况 CSV 全流程 ----
    w._navigate("batch")
    bw = w.batch_workspace
    bw.csv_edit.setText(str(BATCH_CSV))
    app.processEvents()
    bw.validate()
    wait(app, lambda: bw.parsed is not None, 60, "batch parse")
    app.processEvents()
    bw.run()
    wait(app, lambda: w.workflow.report is not None, 180, "batch run")
    app.processEvents()
    shot(app, w, "02_batch_real.png")

    # ---- 5. 历史页：主追溯库真实任务记录 ----
    w._navigate("history")
    app.processEvents()
    wait(app, lambda: w.history_workspace.model.rowCount() > 0, 60, "history rows")
    app.processEvents()
    shot(app, w, "03_history_real.png")

    drain(app, w)
    w.close()
    print("main mode done")


def registry_mode():
    demo = OUT / "registry_demo"
    if demo.exists():
        shutil.rmtree(demo)
    demo.mkdir(parents=True)
    db = demo / "trace.sqlite"

    # 1) 无界面注册三个真实部署模型（复制品落入 demo/registered_models/）
    from damage_gui.model.registry import load_model
    from damage_gui.services.model_registry_service import ModelRegistryService

    svc = ModelRegistryService(db)
    for lv in ("F", "M", "P"):
        bundle = load_model(MODEL_DIR / f"damagelab_pod_rbf_{lv}.joblib")
        info = svc.register(bundle)
        print("registered", lv, info["model_id"][:8])

    # 2) GUI 打开模型库页
    app, w = make_app(db)
    model_path = MODEL_DIR / "damagelab_pod_rbf_F.joblib"
    w._prediction_panel._bind_bundle(load_model(model_path), str(model_path))
    app.processEvents()
    w._navigate("models")
    rw = w.registry_workspace
    wait(app, lambda: bool(getattr(rw, "rows", None)), 60, "registry rows")
    wait(app, lambda: rw.info is not None, 60, "registry detail")
    app.processEvents()
    shot(app, w, "04_models_real.png")

    drain(app, w)
    w.close()
    print("registry mode done")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    (main_mode if mode == "main" else registry_mode)()
