"""Qt aim optimization workspace backed by the shared AimService."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from damage_gui.data.preprocessing import coordinate_axes
from damage_gui.qt.theme import INPUT_HEIGHT, LG, MD, PRIMARY_HEIGHT
from damage_gui.qt.widgets.field_view import FieldView
from damage_gui.qt.widgets.workspace import WorkspaceHeader
from damage_gui.services.aim_service import AimService
from damage_gui.visualization.plots import render_aim_optimization


class AimWorkspace(QWidget):
    completed = Signal(object)
    message = Signal(str, str)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.prediction = None
        self.config = None
        self.result = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.header = WorkspaceHeader()
        self.header.setContentsMargins(16, 8, 16, 0)
        self.view = FieldView()
        self.view.style_figure = self._style_figure
        self.view.translate_figure = self._translate_figure
        layout.addWidget(self.header)
        layout.addWidget(self.view, 1)

        self.inspector = QWidget()
        form = QVBoxLayout(self.inspector)
        form.setContentsMargins(LG, MD, LG, MD)
        form.setSpacing(7)
        self.mode = QComboBox()
        self.mode.addItem("CEP", "CEP")
        self.mode.addItem("REP / DEP", "REP_DEP")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.cep = self._spin(0, 100000, 5, " m")
        self.rep = self._spin(0, 100000, 2, " m")
        self.dep = self._spin(0, 100000, 2, " m")
        self.rho = self._spin(-0.99, 0.99, 0, "", 3)
        self.rotation = QCheckBox()
        self.rotation.toggled.connect(self._mode_changed)
        self.theta = self._spin(-180, 180, 0, "°")
        self.reliability = self._spin(0.001, 1, 1, "", 3)
        self.inputs = []
        for key, widget in (
            ("mode", self.mode), ("cep", self.cep), ("rep", self.rep),
            ("dep", self.dep), ("rho", self.rho), ("rotation", self.rotation),
            ("theta", self.theta), ("reliability", self.reliability),
        ):
            label = QLabel()
            label.setProperty("role", "field")
            form.addWidget(label)
            form.addWidget(widget)
            self.inputs.append((key, label, widget))
        self.run_button = QPushButton()
        self.run_button.setProperty("role", "primary")
        self.run_button.setFixedHeight(PRIMARY_HEIGHT)
        self.run_button.clicked.connect(self.optimize)
        form.addWidget(self.run_button)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addWidget(self.summary)
        form.addStretch()
        self._mode_changed()
        self.set_prediction(None, None)
        self.retranslate()

    @staticmethod
    def _spin(low, high, value, suffix, decimals=2):
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setFixedHeight(INPUT_HEIGHT)
        return spin

    def _mode_changed(self):
        elliptical = self.mode.currentData() == "REP_DEP"
        for key, _label, widget in self.inputs:
            if key == "cep":
                visible = not elliptical
            elif key in ("rep", "dep", "rho", "rotation", "theta"):
                visible = elliptical
            else:
                visible = True
            if key == "rho" and self.rotation.isChecked():
                visible = False
            if key == "theta" and not self.rotation.isChecked():
                visible = False
            widget.setVisible(visible)
            _label.setVisible(visible and key != "rotation")

    def set_prediction(self, prediction, config):
        self.prediction = prediction
        self.config = config
        self.result = None
        self.view.clear()
        self.view._loaded = prediction is not None
        self.run_button.setEnabled(prediction is not None)
        self.retranslate()

    def set_busy(self, busy):
        self.run_button.setEnabled(self.prediction is not None and not busy)

    def optimize(self):
        if self.prediction is None or not self.run_button.isEnabled():
            return
        try:
            x_axis, y_axis = coordinate_axes(self.prediction.shape, self.config)
            elliptical = self.mode.currentData() == "REP_DEP"
            result = AimService().optimize(
                self.prediction, x_axis, y_axis,
                spread_mode="REP_DEP" if elliptical else "CEP",
                cep=self.cep.value() if not elliptical else None,
                rep=self.rep.value() if elliptical else None,
                dep=self.dep.value() if elliptical else None,
                rho=self.rho.value() if elliptical and not self.rotation.isChecked() else 0.0,
                theta_deg=self.theta.value() if elliptical and self.rotation.isChecked() else None,
                reliability=self.reliability.value(),
            )
            figure = render_aim_optimization(self.prediction, result, self.config)
            self.result = result
            self.view.show_figure(figure)
        except Exception as exc:
            self.result = None
            QMessageBox.critical(self, self._copy("error"), str(exc))
            self.message.emit(str(exc), "error")
            return
        self.header.set_status("SUCCESS")
        self._show_result()
        self.completed.emit(result)
        self.message.emit(self._copy("done"), "ok")

    def _copy(self, key):
        zh = self.translator.language == "zh"
        values = {
            "title": ("瞄准优化", "Aim Optimization"),
            "context": ("基于当前预测场计算最优瞄准点", "Find the best aim point for the current prediction"),
            "ready": ("请先运行一次预测。", "Run a prediction first."),
            "empty": ("暂无优化结果。", "No optimization yet."),
            "mode": ("散布模式", "Dispersion mode"),
            "cep": ("CEP", "CEP"), "rep": ("REP", "REP"), "dep": ("DEP", "DEP"),
            "rho": ("相关系数 ρ", "Correlation ρ"),
            "rotation": ("使用旋转角 θ", "Use rotation angle θ"),
            "theta": ("旋转角 θ", "Rotation θ"),
            "reliability": ("可靠度 R", "Reliability R"),
            "run": ("优化瞄准点", "Optimize Aim Point"),
            "best": ("最佳瞄准点", "Best aim point"),
            "gain": ("相对增益", "Relative gain"),
            "shift": ("偏移距离", "Shift distance"),
            "error": ("瞄准优化失败", "Aim optimization failed"),
            "done": ("瞄准优化完成", "Aim optimization complete"),
        }
        return values[key][0 if zh else 1]

    def _show_result(self):
        result = self.result
        if result is None:
            self.summary.setText(self._copy("empty") if self.prediction is not None else self._copy("ready"))
            return
        self.summary.setText(
            f"{self._copy('best')}: ({result.best_x:.1f}, {result.best_y:.1f}) m\n"
            f"Vmax: {result.vmax:.4f}\n"
            f"{self._copy('gain')}: {result.gain_relative:+.2%}\n"
            f"{self._copy('shift')}: {result.shift_distance:.1f} m\n"
            f"σx={result.sigma_x:.1f} m, σy={result.sigma_y:.1f} m, ρ={result.rho:.2f}"
        )

    def _style_figure(self, figure):
        from damage_gui.qt.theme import VIEWPORT_BG

        figure.patch.set_facecolor(VIEWPORT_BG)
        for axis in figure.axes:
            axis.set_facecolor(VIEWPORT_BG)
            axis.tick_params(colors="#b9c3ce")
            axis.xaxis.label.set_color("#b9c3ce")
            axis.yaxis.label.set_color("#b9c3ce")
            for spine in axis.spines.values():
                spine.set_color("#596575")
        self._translate_figure(figure)

    def _translate_figure(self, figure):
        zh = self.translator.language == "zh"
        titles = (("毁伤场 D", "Damage Field D"),
                  ("期望毁伤效能 V", "Expected Damage Value V"))
        image_axes = [axis for axis in figure.axes if axis.images]
        for index, axis in enumerate(image_axes[:2]):
            if index == 0:
                axis.images[0].set_cmap("cividis")
            suffix = ""
            if index == 1 and self.result is not None and self.result.rho:
                suffix = f"\n(σx={self.result.sigma_x:.1f}, σy={self.result.sigma_y:.1f}, ρ={self.result.rho:.2f})"
            axis.set_title(titles[index][0 if zh else 1] + suffix, color="#e4eaf0")
            colorbar = axis.images[0].colorbar
            if colorbar is not None:
                colorbar.set_label(("毁伤值" if index == 0 else "期望毁伤效能") if zh
                                   else ("Damage" if index == 0 else "Expected value"),
                                   color="#b9c3ce")
                colorbar.ax.tick_params(colors="#b9c3ce")
        if self.result is not None and len(image_axes) > 1:
            annotations = image_axes[1].texts
            if annotations:
                annotations[0].set_text(
                    f"★ {self._copy('best')}\n"
                    f"({self.result.best_x:.1f}, {self.result.best_y:.1f}) m\n"
                    f"Vmax={self.result.vmax:.4f}"
                )
            if len(annotations) > 1:
                annotations[1].set_text(
                    f"× {'毁伤峰值' if zh else 'Damage peak'}\n"
                    f"({self.result.d_peak_x:.1f}, {self.result.d_peak_y:.1f}) m"
                )
                annotations[1].set_position((-12, -45))

    def retranslate(self):
        zh = self.translator.language == "zh"
        self.header.title.setText(self._copy("title"))
        self.header.context.setText(self._copy("context") if self.prediction is not None else self._copy("ready"))
        for key, label, _widget in self.inputs:
            label.setText("" if key == "rotation" else self._copy(key))
        self.rotation.setText(self._copy("rotation"))
        self.run_button.setText(self._copy("run"))
        self.view.retranslate(zh)
        self._show_result()
