"""Phase 2.5 — Native desktop release acceptance (Qt).

Covers the release-blocking checks that don't need a human at the screen:

1.  cold start with a completely fresh data dir (no config/db/model)
2.  first-run empty state
3.  window sizes 1100x700 / 1280x720 / 1440x900 / 1600x1000 + maximized
4.  full workflow on unicode + spaces paths (train → save → load →
    predict → validation → batch → history → registry → PNG export)
5.  corrupt inputs (garbage joblib / broken sidecar JSON / invalid CSV)
6.  read-only export target
7.  close confirmation while a job is running
8.  About dialog version display
9.  performance smoke (startup / prediction / history / registry)
10. memory smoke (20 predictions, 5 validations, plot lifecycle)

HiDPI (2x) screenshots run in a separate process: the script re-execs
itself with QT_SCALE_FACTOR=2 when --hidpi is given.

Usage:
    PYTHONPATH=src python scripts/qt_release_acceptance.py [outdir]
"""
from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

RESULTS: dict = {"checks": [], "timings": {}, "memory": {}}


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def rss_kb() -> int:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())],
                         capture_output=True, text=True)
    return int(out.stdout.strip() or 0)


def main(outdir: Path, hidpi: bool = False) -> None:
    from synthetic_data import make_service, write_synthetic_dataset

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["DAMAGE_GUI_DB"] = str(outdir / f"acceptance_{uuid.uuid4().hex[:6]}.sqlite")
    os.environ.setdefault("DAMAGE_GUI_HOME", str(outdir / "cold_home"))
    Path(os.environ["DAMAGE_GUI_HOME"]).mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    from damage_gui.model.registry import load_model, save_model
    from damage_gui.qt.main_window import DamageQtMainWindow
    from damage_gui.qt.theme import build_stylesheet

    suffix = "_hidpi" if hidpi else ""

    def shot(widget, name):
        widget.grab().save(str(outdir / f"{name}{suffix}.png"))

    # ---------- 1/2. cold start + first run ----------
    t0 = time.perf_counter()
    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    w = DamageQtMainWindow()
    w.show()
    app.processEvents()
    startup_ms = (time.perf_counter() - t0) * 1000
    RESULTS["timings"]["startup_window_ms"] = round(startup_ms)

    check("cold-start: window constructed", True, f"{startup_ms:.0f} ms")
    check("cold-start: no model empty state",
          w.top_model.text().lower().startswith(("no model", "尚未")),
          repr(w.top_model.text()))
    check("cold-start: viewport placeholder visible",
          w._field_view.stack.currentIndex() == 0)
    w._navigate("models")
    _wait(app, lambda: w.registry_workspace.empty is not None
          and w.registry_workspace.empty.isVisible(), 15)
    check("first-run: registry empty state visible",
          w.registry_workspace.empty is not None and w.registry_workspace.empty.isVisible())
    shot(w, "01_cold_start_empty" if not hidpi else "90_hidpi_empty")

    # ---------- 3. window sizes ----------
    for width, height in ((1100, 700), (1280, 720), (1440, 900), (1600, 1000)):
        w.resize(width, height)
        w._reset_layout()
        app.processEvents()
        rail_ok = w.rail.isVisible() and w.rail.width() > 0
        insp_ok = w.inspector.isVisible() and w.inspector.width() >= 200
        act_ok = w._activity.isVisible()
        shot(w, f"02_size_{width}x{height}")
        check(f"layout {width}x{height}", rail_ok and insp_ok and act_ok,
              f"rail={w.rail.width()} inspector={w.inspector.width()}")
    w.resize(1280, 720)
    w.showMaximized()
    app.processEvents()
    shot(w, "03_maximized_1280x720")
    check("layout maximized", w.isMaximized())
    w.showNormal()

    if hidpi:  # 2x pass only needs visual evidence
        dpr = w.devicePixelRatioF()
        shot(w, "91_hidpi_prediction")
        check("hidpi: devicePixelRatio == 2", abs(dpr - 2.0) < 0.01, f"dpr={dpr}")
        _summary(outdir, suffix)
        return

    # ---------- 4. unicode + spaces workflow ----------
    work = outdir / "Damage Lab 测试 数据"
    work.mkdir(parents=True, exist_ok=True)
    dataset = work / "synthetic_dataset"
    dataset.mkdir(exist_ok=True)
    write_synthetic_dataset(dataset, velocities=(100., 200., 300.), angles=(10., 20., 30.))

    bundle = make_service(dataset).train_bundle("F")
    model_path = work / "模型 F test.joblib"
    save_model(bundle, model_path)
    check("unicode+spaces: model saved", model_path.is_file(), str(model_path.name))

    loaded = load_model(model_path)
    panel = w._prediction_panel
    panel._bind_bundle(loaded, str(model_path))
    app.processEvents()
    check("unicode+spaces: model loaded", panel.bundle is not None)

    # prediction latency
    panel.h_spin.setValue(2)
    panel.v_spin.setValue(200)
    panel.deg_spin.setValue(20)
    t0 = time.perf_counter()
    w._run_current()
    _wait(app, lambda: not panel.is_running, 60)
    predict_ms = (time.perf_counter() - t0) * 1000
    RESULTS["timings"]["prediction_ms"] = round(predict_ms)
    check("unicode+spaces: prediction", panel.current_result is not None,
          f"{predict_ms:.0f} ms")
    shot(w, "04_prediction_loaded")

    # PNG export to unicode path
    png_path = work / "导出 图像 test.png"
    orig_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *a, **k: (str(png_path), "")
    w._field_view.buttons["Export"].click()
    app.processEvents()
    QFileDialog.getSaveFileName = orig_save
    check("unicode+spaces: PNG export", png_path.is_file(), str(png_path.name))

    # validation
    validation = w.validation_workspace
    w._navigate("validation")
    validation.set_bundle(loaded)
    validation.mode.setCurrentIndex(validation.mode.findData("random"))
    _wait(app, validation.run_button.isEnabled, 30)
    t0 = time.perf_counter()
    w._run_current()
    _wait(app, lambda: not w.workflow.validation.running, 120)
    RESULTS["timings"]["validation_ms"] = round((time.perf_counter() - t0) * 1000)
    check("unicode+spaces: validation", validation.result is not None)
    shot(w, "05_validation")

    # batch on unicode path
    batch = w.batch_workspace
    csv_path = work / "批量 测试.csv"
    csv_path.write_text("job_id,h,v,deg,level\n001,2,200,20,F\n002,3,100,10,F\n",
                        encoding="utf-8")
    w._navigate("batch")
    batch.set_bundle(loaded)
    batch.load_csv(str(csv_path))
    batch.validate()
    _wait(app, lambda: batch.run_button.isEnabled(), 30)
    w._run_current()
    _wait(app, lambda: not w.workflow.running, 120)
    check("unicode+spaces: batch", w.workflow.job["status"] == "SUCCESS")

    # history + registry
    t0 = time.perf_counter()
    w._navigate("history")
    _wait(app, lambda: len(w.history_workspace.model.rows) >= 3, 30)
    RESULTS["timings"]["history_first_page_ms"] = round((time.perf_counter() - t0) * 1000)
    check("unicode+spaces: history rows", len(w.history_workspace.model.rows) >= 3)
    shot(w, "06_history")

    # registry: register the trained model, then list (registration is the
    # only path that adds rows — merely loading a model stays "external").
    w._navigate("models")
    _wait(app, lambda: not w.registry_workspace._operation, 15)
    w.registry_workspace.register(loaded)
    _wait(app, lambda: w.registry_workspace.rows and not w.registry_workspace._operation, 60)
    t0 = time.perf_counter()
    w.registry_workspace.refresh()
    _wait(app, lambda: w.registry_workspace.rows and not w.registry_workspace._operation, 30)
    RESULTS["timings"]["registry_load_ms"] = round((time.perf_counter() - t0) * 1000)
    check("unicode+spaces: registry rows", len(w.registry_workspace.rows) >= 1)
    shot(w, "07_registry")

    # ---------- 5. corrupt inputs ----------
    garbage = work / "broken.joblib"
    garbage.write_bytes(b"this is not a joblib file")
    orig_open = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = lambda *a, **k: (str(garbage), "")
    messages = []
    panel.status_message.connect(lambda text, role="error": messages.append((text, role)))
    panel._on_load_model()  # must not raise
    app.processEvents()
    QFileDialog.getOpenFileName = orig_open
    check("corrupt joblib: error surfaced, no crash",
          panel.bundle is not None and messages, str(messages[-1][0])[:60] if messages else "")

    bad_sidecar = work / "模型 F test.joblib"
    sidecar = bad_sidecar.with_name(bad_sidecar.stem + ".meta.json")
    sidecar.write_text("{not valid json", encoding="utf-8")
    try:
        load_model(bad_sidecar)
        sidecar_ok = False
    except Exception as exc:  # friendly ModelLoadError expected
        sidecar_ok = "元数据" in str(exc) or "JSON" in str(exc)
    sidecar.write_text("", encoding="utf-8")  # empty sidecar -> metadata missing
    legacy = load_model(bad_sidecar)  # missing-metadata model still loads
    check("corrupt sidecar JSON: readable error", sidecar_ok)
    check("missing-metadata model: still loads", legacy is not None)

    bad_csv = work / "broken.csv"
    bad_csv.write_text("job_id,h,v,deg\nnotanumber,x,y,z\n", encoding="utf-8")
    batch.load_csv(str(bad_csv))
    batch.validate()
    _wait(app, lambda: "无法读取" in batch.summary.text()
           or "Unable" in batch.summary.text()
           or "Invalid" in batch.summary.text(), 30)
    check("invalid CSV: error shown in summary",
          "无法读取" in batch.summary.text()
          or "Unable" in batch.summary.text()
          or "Invalid" in batch.summary.text())
    shot(w, "08_invalid_csv")

    # ---------- 6. read-only export ----------
    ro_dir = outdir / "read_only_dir"
    ro_dir.mkdir(exist_ok=True)
    ro_dir.chmod(0o555)
    ro_path = ro_dir / "denied.png"
    QFileDialog.getSaveFileName = lambda *a, **k: (str(ro_path), "")
    export_errors = []
    w._field_view.export_message.connect(lambda text, role="info": export_errors.append(role))
    w._navigate("prediction")
    w._field_view.buttons["Export"].click()
    app.processEvents()
    QFileDialog.getSaveFileName = orig_save
    ro_dir.chmod(0o755)
    check("read-only export: error surfaced, no crash", "error" in export_errors,
          str(export_errors))

    # ---------- 7. close confirmation ----------
    asked = []
    QMessageBox.question = staticmethod(
        lambda *a, **k: (asked.append(1), QMessageBox.No)[1])
    w.task_adapter.is_busy = lambda: True  # simulate a running job
    w.close()
    app.processEvents()
    check("close confirmation: dialog shown", len(asked) == 1)
    check("close confirmation: 'No' keeps window open", w.isVisible())
    cancelled = []
    w.workflow.cancel = lambda: cancelled.append("pred")
    w.workflow.validation.cancel = lambda: cancelled.append("val")
    w.workflow.training.cancel = lambda: cancelled.append("train")
    QMessageBox.question = staticmethod(
        lambda *a, **k: (asked.append(1), QMessageBox.Yes)[1])
    w.close()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.01)
    check("close confirmation: 'Yes' cancels all workflows",
          set(cancelled) == {"pred", "val", "train"}, str(cancelled))
    del w.task_adapter.is_busy  # restore the real bound method

    # ---------- 8. About dialog ----------
    about_text = []
    QMessageBox.about = staticmethod(lambda *a, **k: about_text.append(a[-1]))
    w._show_about()
    from damage_gui import __version__
    check("about dialog: version shown",
          about_text and __version__ in about_text[0], about_text[0][:40] if about_text else "")

    # ---------- 9/10. performance + memory smoke ----------
    rss_start = rss_kb()
    from matplotlib.figure import Figure
    for i in range(20):
        panel.h_spin.setValue(1 + (i % 3))
        w._run_current()
        _wait(app, lambda: not panel.is_running, 60)
        if i % 5 == 4:
            shot(w, f"09_memory_pred_{i + 1}")
    for _ in range(5):
        w._navigate("validation")
        w._run_current()
        _wait(app, lambda: not w.workflow.validation.running, 120)
    for _ in range(6):  # plot switches
        w._navigate("prediction")
        w._navigate("history")
        w._navigate("validation")
        app.processEvents()
    gc.collect()
    rss_end = rss_kb()
    figures = [o for o in gc.get_objects() if isinstance(o, Figure)]
    live_canvases = 1  # field view canvas
    RESULTS["memory"]["rss_start_kb"] = rss_start
    RESULTS["memory"]["rss_end_kb"] = rss_end
    RESULTS["memory"]["rss_growth_mb"] = round((rss_end - rss_start) / 1024, 1)
    RESULTS["memory"]["live_figure_objects"] = len(figures)
    check("memory: RSS growth bounded", rss_end - rss_start < 400 * 1024,
          f"+{(rss_end - rss_start) / 1024:.0f} MB")
    check("plot lifecycle: no leaked figures", len(figures) <= live_canvases + 3,
          f"{len(figures)} live Figure objects")

    # language switch smoke (translations intact)
    w.translator.set_language("zh")
    app.processEvents()
    shot(w, "10_chinese")
    check("language switch zh: no crash, menus translated",
          w._menus["file"].title() == "文件", w._menus["file"].title())
    w.translator.set_language("en")

    _summary(outdir, suffix)


def _wait(app, predicate, timeout=60):
    until = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        time.sleep(0.005)
        assert time.monotonic() < until, "acceptance wait timed out"


def _summary(outdir: Path, suffix: str) -> None:
    failed = [c for c in RESULTS["checks"] if not c["ok"]]
    RESULTS["verdict"] = "PASS" if not failed else f"FAIL ({len(failed)})"
    (outdir / f"report{suffix}.json").write_text(
        json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nverdict: {RESULTS['verdict']}")


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "outputs" / "qt_phase25")
    out.mkdir(parents=True, exist_ok=True)
    if "--hidpi" in sys.argv:
        main(out, hidpi=True)
    else:
        main(out, hidpi=False)
        env = dict(os.environ, QT_SCALE_FACTOR="2", QT_AUTO_SCREEN_SCALE_FACTOR="0")
        subprocess.run([sys.executable, __file__, str(out), "--hidpi"], check=True, env=env)
