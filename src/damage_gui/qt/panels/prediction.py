"""Prediction inspector (right dock).

Business flow is unchanged from Phase 1:

    Load Model → 选择 level → 输入 h/v/deg → Predict
        → services.prediction_service.PredictionService.predict(bundle, condition)
        → prediction_completed(result) → 主窗口渲染毁伤场

All scientific work is delegated to :mod:`damage_gui.services`,
:mod:`damage_gui.model` and :mod:`damage_gui.visualization`; this module only
arranges the inspector presentation: INPUT / RESULT / MODEL sections separated
by dividers (no cards, no group boxes).
"""
from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from damage_gui.config import CONDITION_LIMITS
from damage_gui.qt.i18n import qt_text
from damage_gui.qt.theme import INPUT_HEIGHT, LG, MD, PRIMARY_HEIGHT, SM
from damage_gui.qt.widgets.status_badge import StatusBadge

if TYPE_CHECKING:
    from damage_gui.data.loader import Condition, DamageDataManager
    from damage_gui.gui.i18n import Translator
    from damage_gui.model.bundle import ModelBundle
    from damage_gui.services.prediction_service import PredictionResult, PredictionService


class PredictionPanel(QWidget):
    """Inspector column for the Prediction workspace."""

    prediction_completed = Signal(object)
    model_loaded = Signal(object)
    status_message = Signal(str, str)
    error_raised = Signal(str)
    running_changed = Signal(bool)
    prediction_failed = Signal(str)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.bundle: ModelBundle | None = None
        self.data_manager: DamageDataManager | None = None
        self.prediction_service: PredictionService | None = None
        self.current_result: PredictionResult | None = None
        self.model_meta_plain = ""
        self.workflow = None
        self._worker = None
        self._running = False

        self._build()

    # ---------- presentation ----------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(LG, MD, LG, MD)
        outer.setSpacing(0)

        # Model actions live in the application bar; retain lifecycle widget attributes.
        self.model_status_badge = StatusBadge()
        self.model_path_edit = QLineEdit()
        self.load_button = QPushButton()
        self.save_button = QPushButton()
        for widget in (self.model_status_badge, self.model_path_edit,
                       self.load_button, self.save_button):
            widget.setParent(self)
            widget.hide()
        self.save_button.setEnabled(False)

        # --- INPUT ---
        self._section("inspector.input")
        self.level_combo = QComboBox()
        self.level_combo.addItems(list("ABCDEFGH"))
        self.level_combo.setCurrentText("F")
        # A trained bundle has one level. Never imply it can predict another level.
        self.level_combo.setEnabled(False)
        self.h_spin = QDoubleSpinBox()
        self.v_spin = QDoubleSpinBox()
        self.deg_spin = QDoubleSpinBox()
        for spin, key, decimals, value, suffix in (
            (self.h_spin, "h", 2, 0, " m"),
            (self.v_spin, "v", 1, 150, " m/s"),
            (self.deg_spin, "deg", 1, 20, "°"),
        ):
            lo, hi, step = CONDITION_LIMITS[key]
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setValue(value)
            spin.setSuffix(suffix)
            spin.setFixedHeight(INPUT_HEIGHT)
        self.level_combo.setFixedHeight(INPUT_HEIGHT)
        self._input_labels = []
        for key, control in (("panel.damage_level", self.level_combo),
                             ("panel.height", self.h_spin),
                             ("panel.velocity", self.v_spin),
                             ("panel.angle", self.deg_spin)):
            label = QLabel(self.translator.t(key))
            label.setBuddy(control)
            self._input_labels.append((label, key))
            self._field_row(label, control)
        self.predict_button = QPushButton(self.translator.t("panel.run_prediction"))
        self.predict_button.setProperty("role", "primary")
        self.predict_button.setFixedHeight(PRIMARY_HEIGHT)
        self.predict_button.setEnabled(False)
        self.predict_button.clicked.connect(self._on_predict)
        outer.addSpacing(SM)
        outer.addWidget(self.predict_button)

        # --- RESULT ---
        self._divider()
        self._section("inspector.result")
        self.result_values = {}
        self._result_labels = []
        for key, label_key in (("maximum", "results.maximum"),
                               ("area", "results.area"),
                               ("confidence", "results.confidence"),
                               ("time", "results.elapsed")):
            label = QLabel(self.translator.t(label_key))
            self._result_labels.append((label, label_key))
            if key == "confidence":
                value = StatusBadge("—", "neutral")
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            else:
                value = QLabel("—")
                value.setProperty("role", "value")
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.result_values[key] = value
            self._kv_row(label, value)

        # --- MODEL ---
        self._divider()
        self._section("inspector.model")
        self.model_values = {}
        self._model_labels = []
        for key, label_key in (("type", "inspector.type"),
                               ("level", "inspector.level"),
                               ("id", "inspector.model_id")):
            label = QLabel(self.translator.t(label_key))
            self._model_labels.append((label, label_key))
            value = QLabel("—")
            value.setProperty("role", "value")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if key == "id":
                value.setProperty("role", "model-id")
                value.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
            self.model_values[key] = value
            self._kv_row(label, value)
        outer.addStretch()

        # Hidden OOD detail text; shown in the Results activity tab.
        self.reliability_label = QLabel()
        self.reliability_label.setWordWrap(True)
        self.reliability_label.hide()
        outer.addWidget(self.reliability_label)

    def _section(self, key: str) -> None:
        label = QLabel(self.translator.t(key))
        label.setProperty("role", "section")
        setattr(self, f"_section_{key.split('.')[-1]}", label)
        layout = self.layout()
        if key != "inspector.input":
            layout.addSpacing(LG)
        layout.addWidget(label)
        layout.addSpacing(8)

    def _divider(self) -> None:
        line = QFrame()
        line.setProperty("role", "divider")
        line.setFrameShape(QFrame.NoFrame)
        line.setFixedHeight(1)
        self.layout().addSpacing(LG)
        self.layout().addWidget(line)

    def _field_row(self, label: QLabel, control: QWidget) -> None:
        row = QVBoxLayout()
        row.setSpacing(4)
        label.setProperty("role", "field")
        row.addWidget(label)
        row.addWidget(control)
        self.layout().addLayout(row)
        self.layout().addSpacing(8)

    def _kv_row(self, label: QLabel, value: QWidget) -> None:
        label.setProperty("role", "field")
        label.setMinimumHeight(24)
        value.setMinimumHeight(24)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value)
        self.layout().addLayout(row)
        self.layout().addSpacing(0)

    def retranslate(self):
        for label, key in self._input_labels:
            label.setText(self.translator.t(key))
        for label, key in self._result_labels:
            label.setText(self.translator.t(key))
        for label, key in self._model_labels:
            label.setText(self.translator.t(key))
        self.predict_button.setText(qt_text("running", self.translator.language == "zh")
                                    if self._running else self.translator.t("panel.run_prediction"))
        for widget, key in ((self._section_input, "inspector.input"),
                            (self._section_result, "inspector.result"),
                            (self._section_model, "inspector.model")):
            widget.setText(self.translator.t(key))
        if self.bundle is not None:
            self._update_model_rows()
        if self.current_result is not None:
            self._update_reliability(self.current_result)
            self._update_result_rows(self.current_result)

    # ---------- model lifecycle (unchanged logic) ----------

    def _on_load_model(self) -> None:
        if self._running or (self.workflow and self.workflow.scientific_busy):
            return
        try:
            from damage_gui.model.registry import load_model

            model_path, _ = QFileDialog.getOpenFileName(
                self,
                self.translator.t("panel.load"),
                "",
                "Joblib Model (*.joblib);;All Files (*)",
            )
            if not model_path:
                return
            bundle = load_model(model_path)
            self._bind_bundle(bundle, model_path)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger("damage_gui.qt").exception("Model load failed")
            self.status_message.emit(str(exc),"error")
            self.error_raised.emit(str(exc))

    def _bind_bundle(self, bundle: ModelBundle, path: str) -> None:
        self.bundle = bundle
        self.current_result = None
        self.result_values["confidence"].setToolTip("")
        self.reliability_label.clear()
        self.level_combo.setCurrentText(bundle.level)
        self.model_path_edit.setText(path)
        self.model_path_edit.setToolTip(path)
        self.model_status_badge.set_status(self.translator.t("nav.model"), "info")
        self.save_button.setEnabled(True)
        self.predict_button.setEnabled(True)
        for value in self.result_values.values():
            if isinstance(value, StatusBadge):
                value.set_status("—")
            else:
                value.setText("—")
        self._update_model_rows()

        from damage_gui.data.loader import DamageDataManager
        from damage_gui.services.prediction_service import PredictionService

        resolved_config = bundle.resolved_config()
        self.data_manager = DamageDataManager(bundle.data_dir) if bundle.data_dir else None
        self.prediction_service = PredictionService(
            self.data_manager,
            config=resolved_config,
        )
        self.model_loaded.emit(bundle)

    def _update_model_rows(self) -> None:
        bundle = self.bundle
        if bundle is None:
            return
        name = getattr(bundle.model, "model_name", type(bundle.model).__name__)
        meta = getattr(bundle, "metadata", None)
        model_id = meta.model_id if meta else self.translator.t("model.legacy")
        self.model_meta_plain = f"{bundle.level} · {name} / {model_id}"
        self.model_values["type"].setText(name)
        self.model_values["level"].setText(bundle.level)
        short_id = model_id if len(model_id) <= 12 else f"{model_id[:10]}…"
        self.model_values["id"].setText(short_id)
        self.model_values["id"].setToolTip(model_id)

    def _on_save_model(self) -> None:
        if self.bundle is None:
            return
        from damage_gui.model.registry import save_model

        path, _ = QFileDialog.getSaveFileName(
            self,
            self.translator.t("panel.save"),
            f"damage_model_{self.bundle.level}.joblib",
            "Joblib Model (*.joblib)",
        )
        if not path:
            return
        try:
            save_model(self.bundle, path)
            self.status_message.emit(
                f"{'模型已保存' if self.translator.language=='zh' else 'Model saved'}: {__import__('pathlib').Path(path).name}", "ok"
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.translator.t("status.error"), str(exc))

    # ---------- prediction (unchanged logic) ----------

    def _current_condition(self) -> Condition:
        from damage_gui.services.conditions import validate_condition

        values = {
            "h": float(self.h_spin.value()),
            "v": float(self.v_spin.value()),
            "deg": float(self.deg_spin.value()),
        }
        return validate_condition(**values)

    @property
    def is_running(self):
        return self._running

    def _set_running(self, running):
        self._running = running
        self.predict_button.setEnabled(not running and self.bundle is not None)
        self.predict_button.setText(qt_text("running", self.translator.language == "zh")
                                    if running else self.translator.t("panel.run_prediction"))
        for control in (self.h_spin, self.v_spin, self.deg_spin):
            control.setEnabled(not running)
        self.running_changed.emit(running)

    def _on_predict(self) -> None:
        if self._running or self.bundle is None or self.prediction_service is None:
            return
        if self.level_combo.currentText() != self.bundle.level:
            self.status_message.emit(qt_text('model_level_mismatch', self.translator.language == 'zh'), 'warning')
            return
        try:
            condition = self._current_condition()
            self.bundle.resolved_config()
        except Exception:
            logging.getLogger("damage_gui.qt.prediction").exception("Invalid prediction input")
            self._report_failure(traceback.format_exc())
            return
        if self.workflow is None or self.workflow.scientific_busy:
            self.status_message.emit(qt_text('shared_model_busy', self.translator.language == 'zh'), 'warning')
            return
        self._set_running(True)
        self.status_message.emit(self.translator.t("status.running"), "busy")
        self._worker = self.workflow.run_prediction(self.prediction_service, self.bundle, condition,
                                                     self.model_path_edit.text())

    def bind_workflow(self, workflow):
        self.workflow = workflow
        workflow.prediction_finished.connect(self._finish_prediction)

    def _finish_prediction(self, completion):
        from damage_gui.qt.i18n import qt_text
        job, state = completion
        try:
            result = state['result']
            if job['status'] == 'SUCCESS' and result is not None:
                self.current_result = result
                self._update_reliability(result)
                self._update_result_rows(result)
                self.prediction_completed.emit(result)
                self.status_message.emit(
                    f"{self.translator.t('status.complete')} — {result.elapsed_ms} ms" if state['persisted'] else
                    qt_text('persistence_failed', self.translator.language == 'zh'),
                    'ok' if state['persisted'] else 'warning')
            elif job['status'] == 'CANCELLED':
                self.status_message.emit(qt_text('cancelled', self.translator.language == 'zh'), 'warning')
            else:
                self._report_failure(job.get('error') or qt_text('failed', self.translator.language == 'zh'))
            if not state['persisted'] and job['status'] != 'SUCCESS':
                self.status_message.emit(qt_text('failed' if job['status'] == 'FAILED' else 'cancelled', self.translator.language == 'zh') + ' · ' + qt_text('history_write_failed', self.translator.language == 'zh'), 'warning')
        finally:
            self._worker = None
            self._set_running(False)

    def _report_failure(self, trace):
        message = qt_text("failed", self.translator.language == "zh")
        self.error_raised.emit(trace)
        self.prediction_failed.emit(message)
        self.status_message.emit(message, "error")

    def _update_result_rows(self, result: PredictionResult) -> None:
        self.result_values["maximum"].setText(f"{result.peak_intensity:.3f}")
        self.result_values["area"].setText(f"{result.damage_area_ratio:.1%}")
        self.result_values["time"].setText(f"{result.elapsed_ms} ms")
        report = result.ood_report
        confidence = report.level.upper() if report else "—"
        role = {"high": "success", "medium": "warning", "low": "error"}.get(
            report.level if report else "", "neutral")
        self.result_values["confidence"].set_status(confidence, role)
        self.result_values["confidence"].setToolTip(self.reliability_label.text())

    def _update_reliability(self, result: PredictionResult) -> None:
        report = result.ood_report
        if report is None:
            self.reliability_label.setText(self.translator.t("status.no_ood"))
            self.reliability_label.setProperty("role", "status-info")
        else:
            lines = []
            confidence_key = {
                "high": "ood.high",
                "medium": "ood.medium",
                "low": "ood.low",
            }.get(report.level, "common.unknown")
            lines.append(
                f"{self.translator.t('results.confidence')}: {self.translator.t(confidence_key)}"
            )
            lines.append(
                f"{self.translator.t('results.ood_distance')}: {report.distance:.3f}"
            )
            inside = getattr(report, "in_hull", None)
            if inside is False:
                lines.append(self.translator.t("common.outside_hull"))
            local = getattr(report, "local_support", None)
            if local is False:
                lines.append(self.translator.t("common.sparse_support"))
            self.reliability_label.setText("\n".join(lines))
            role = "error" if report.is_extrapolation else "success"
            self.reliability_label.setProperty("role", f"status-{role}")
        self.reliability_label.style().unpolish(self.reliability_label)
        self.reliability_label.style().polish(self.reliability_label)


__all__ = ["PredictionPanel"]
