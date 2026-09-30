"""Dark scientific canvas with compact viewport tools and a data probe.

The application shell stays light; this viewport renders Matplotlib figures on
a dark surface. Figures are restyled after rendering (backgrounds, ticks,
labels, titles, colorbars) — the data and scientific results are untouched.
"""
from datetime import datetime

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from damage_gui.qt import theme as qt_theme
from damage_gui.qt.i18n import qt_text
from damage_gui.qt.icons import IconToolButton
from damage_gui.visualization.scientific_theme import (
    apply_scientific_theme,
    translate_scientific_figure,
)


class FieldView(QWidget):
    export_message = Signal(str,str)
    load_requested = Signal()

    def __init__(self, parent=None, *, with_toolbar=True):
        super().__init__(parent)
        self.setObjectName('viewport')
        self._probe_cid = None
        self._zh = False
        self._running = False
        self._failed = False
        self._has_result = False
        self.export_model_name = "damage"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QWidget()
        bar.setObjectName('viewportBar')
        actions = QHBoxLayout(bar)
        actions.setContentsMargins(12, 3, 8, 3)
        actions.setSpacing(2)
        self.probe_readout = QLabel('')
        self.probe_readout.setProperty('role', 'probe-readout')
        self.probe_readout.setMinimumWidth(170)
        actions.addWidget(self.probe_readout)
        actions.addStretch()
        self._canvas = FigureCanvasQTAgg(Figure(constrained_layout=True))
        self._canvas.setMinimumSize(300, 180)
        self._canvas.setFocusPolicy(Qt.StrongFocus)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        self._toolbar.hide()
        self.buttons = {}
        for text, callback in (('Reset', self._toolbar.home), ('Pan', self._toolbar.pan),
                               ('Zoom', self._toolbar.zoom), ('Probe', None),
                               ('Export', self.export_figure)):
            button = IconToolButton(text.lower(), dark=True)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setText(text)
            button.setFixedHeight(28)
            button.setProperty('role', 'view-tool')
            button.setCheckable(text in ('Pan', 'Zoom', 'Probe'))
            if callback is not None:
                button.clicked.connect(callback)
            if text in ('Pan', 'Zoom'):
                button.clicked.connect(self._sync_modes)
            if text == 'Probe':
                button.toggled.connect(self._set_probe)
            actions.addWidget(button)
            self.buttons[text] = button
        if with_toolbar:
            layout.addWidget(bar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("viewportStack")
        empty = QWidget()
        empty.setObjectName("viewportEmpty")
        center = QVBoxLayout(empty)
        center.setSpacing(qt_theme.SM)
        center.addStretch()
        self.empty_title = QLabel()
        self.empty_title.setProperty('role', 'empty-title')
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_body = QLabel()
        self.empty_body.setProperty('role', 'empty-body')
        self.empty_body.setAlignment(Qt.AlignCenter)
        self.load_button = QPushButton()
        self.load_button.setFixedHeight(32)
        self.load_button.setProperty("role", "empty-action")
        self.load_button.clicked.connect(self.load_requested)
        center.addWidget(self.empty_title)
        center.addWidget(self.empty_body)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.load_button)
        row.addStretch()
        center.addLayout(row)
        center.addStretch()
        self.stack.addWidget(empty)
        self.stack.addWidget(self._canvas)
        layout.addWidget(self.stack, 1)
        self._loaded = False
        self.retranslate(False)
        self.clear()

    def retranslate(self, zh):
        self._zh = zh
        for key, text in zip(self.buttons, ('复位', '平移', '缩放', '探针', '导出'), strict=False):
            self.buttons[key].setText(text if zh else key)
            self.buttons[key].setToolTip(text if zh else key)
            self.buttons[key].setAccessibleName(text if zh else key)
        if self._running:
            self.empty_title.setText(qt_text('running_title', zh))
            self.empty_body.setText('')
        elif self._failed:
            self.empty_title.setText(qt_text('failed', zh))
            self.empty_body.setText(qt_text('failed_body', zh))
        elif self._loaded:
            self.empty_title.setText(qt_text('ready_title', zh))
            self.empty_body.setText(qt_text('ready_body', zh))
        else:
            self.empty_title.setText('尚未加载模型' if zh else 'No model loaded')
            self.empty_body.setText('加载模型后开始毁伤场预测' if zh
                                    else 'Load a model to begin prediction.')
        self.load_button.setText('加载模型' if zh else 'Load Model')
        self.load_button.setVisible(not self._loaded and not self._running)
        if self._has_result:
            if self._failed:
                self.probe_readout.setText(qt_text("failed", zh))
            self._translate_figure()
            self._canvas.draw_idle()

    def _sync_modes(self):
        mode = self._toolbar.mode.name
        self.buttons['Pan'].setChecked(mode == 'PAN')
        self.buttons['Zoom'].setChecked(mode == 'ZOOM')

    # ---- probe ----

    def _set_probe(self, active):
        if active:
            self._probe_cid = self._canvas.mpl_connect('motion_notify_event', self._on_probe)
        else:
            if self._probe_cid is not None:
                self._canvas.mpl_disconnect(self._probe_cid)
            self._probe_cid = None
            self.probe_readout.setText('')

    def _on_probe(self, event):
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            self.probe_readout.setText('')
            return
        value = self._image_value(event.inaxes, event.xdata, event.ydata)
        text = '—' if value is None else f'{value:.3f}'
        self.probe_readout.setText(f'x = {event.xdata:.1f}   y = {event.ydata:.1f}   value = {text}')

    @staticmethod
    def _image_value(axis, x, y):
        """Read the intensity under the cursor from the first raster image."""
        for image in getattr(axis, 'images', []):
            array = image.get_array()
            x0, x1, y0, y1 = image.get_extent()
            nrows, ncols = array.shape[0], array.shape[1]
            if x1 == x0 or y1 == y0:
                continue
            col = (x - x0) / (x1 - x0) * ncols
            if image.get_origin() == 'upper':
                row = (y1 - y) / (y1 - y0) * nrows
            else:
                row = (y - y0) / (y1 - y0) * nrows
            r, c = int(row), int(col)
            if 0 <= r < nrows and 0 <= c < ncols:
                cell = array[r, c]
                if np.ma.is_masked(cell) or np.isnan(float(cell)):
                    return None
                return float(cell)
        return None

    # ---- figure handling ----

    @property
    def figure(self):
        return self._canvas.figure

    def show_figure(self, source):
        if source is None:
            self.clear()
            return
        # Leave navigation mode before replacing axes; reset history to the new figure.
        if self._toolbar.mode.name == 'PAN':
            self._toolbar.pan()
        elif self._toolbar.mode.name == 'ZOOM':
            self._toolbar.zoom()
        self.stack.setCurrentIndex(1)
        old = self._canvas.figure
        self._canvas.figure = source
        if old is not source:
            old.clear()
            old.set_canvas(None)
        source.set_canvas(self._canvas)
        source.set_dpi(source._original_dpi * self._canvas.device_pixel_ratio)
        source.set_size_inches(self._canvas.width() * self._canvas.device_pixel_ratio / source.dpi,
                               self._canvas.height() * self._canvas.device_pixel_ratio / source.dpi, forward=False)
        self._has_result = True
        self._failed = False
        self.probe_readout.clear()
        apply_scientific_theme(source, 'zh' if self._zh else 'en')
        self._toolbar.update()
        self._sync_modes()
        self.stack.setCurrentIndex(1)
        for button in self.buttons.values():
            button.setEnabled(not self._running)
        self._canvas.draw_idle()

    def clear(self):
        if self._toolbar.mode.name == 'PAN':
            self._toolbar.pan()
        elif self._toolbar.mode.name == 'ZOOM':
            self._toolbar.zoom()
        figure = Figure(constrained_layout=True)
        figure.patch.set_facecolor(qt_theme.VIEWPORT_BG)
        old = self._canvas.figure
        self._canvas.figure = figure
        old.clear()
        old.set_canvas(None)
        figure.set_canvas(self._canvas)
        self._has_result = False
        self._failed = False
        self.buttons["Probe"].setChecked(False)
        self.probe_readout.clear()
        self._sync_modes()
        self.stack.setCurrentIndex(0)
        for button in self.buttons.values():
            button.setEnabled(False)
        self._toolbar.update()


    def _translate_figure(self):
        translate_scientific_figure(self.figure, 'zh' if self._zh else 'en')

    def set_running(self, running):
        self._running = running
        if running:
            self._failed = False
            self.probe_readout.clear()
        for button in self.buttons.values():
            button.setEnabled(self._has_result and not running)
        self.retranslate(self._zh)

    def show_error(self):
        self._failed = True
        self.buttons["Probe"].setChecked(False)
        if self._has_result:
            self.probe_readout.setText(qt_text("failed", self._zh))
        if not self._has_result:
            self.stack.setCurrentIndex(0)
        self.retranslate(self._zh)

    def export_figure(self):
        if not self._has_result or self._running:
            return
        name = f"{self.export_model_name}_{datetime.now():%Y%m%d_%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(self, '导出图像' if self._zh else 'Export Figure',
                                            name, 'PNG (*.png)')
        if path:
            if not path.lower().endswith('.png'):
                path += '.png'
            try:
                self.figure.savefig(path, dpi=300, facecolor=qt_theme.VIEWPORT_BG)
                from pathlib import Path

                from damage_gui.qt.widgets.workspace import ux
                self.export_message.emit(ux('exported',self._zh)+' · '+Path(path).name,'ok')
            except OSError as exc:
                import logging
                logging.getLogger('damage_gui.qt').exception('Figure export failed')
                self.export_message.emit(str(exc),'error')
