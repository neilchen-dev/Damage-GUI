"""Collapsible bottom dock: Jobs / Results / Logs tabs plus a status readout."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from damage_gui.batch.schema import OUTPUT_COLUMNS
from damage_gui.qt.i18n import Translator, qt_text
from damage_gui.qt.icons import icon
from damage_gui.qt.theme import QtTheme
from damage_gui.qt.widgets.status_badge import StatusIndicator
from damage_gui.qt.widgets.workspace import DetailView, ux
from damage_gui.qt.workflow import table

COLLAPSED_HEIGHT = 34
EXPANDED_MIN = 180


class ActivityPanel(QWidget):
    """Desktop-style activity dock: a 34 px strip that expands to a tabbed panel."""

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("activityPanel")
        self._collapsed = True
        self.result_kind = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        strip = QWidget()
        strip.setFixedHeight(COLLAPSED_HEIGHT)
        row = QHBoxLayout(strip)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(2)
        self._tabs = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key in ("jobs", "results", "logs"):
            button = QToolButton()
            button.setCheckable(True)
            button.setProperty("role", "tab")
            self._group.addButton(button)
            row.addWidget(button)
            self._tabs[key] = button
        self._tabs["jobs"].setChecked(True)
        row.addStretch()
        self.status = StatusIndicator("Ready", "neutral")
        row.addWidget(self.status)
        self.toggle = QToolButton()
        self.toggle.setProperty("role", "collapse")
        self.toggle.setFixedHeight(20)
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._on_toggle)
        row.addWidget(self.toggle)
        root.addWidget(strip)

        self.stack = QStackedWidget()
        self.stack.setObjectName("activityContent")
        self.jobs, self.jobs_model = table(('type','status','detail','progress','elapsed'))
        self.result_table, self.result_model = table(OUTPUT_COLUMNS)
        self.results = DetailView()
        self.results.setReadOnly(True)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(500)
        self.stack.addWidget(self.jobs)
        self.stack.addWidget(self.results)
        self.stack.addWidget(self.logs)
        self.stack.addWidget(self.result_table)
        self.stack.hide()
        root.addWidget(self.stack, 1)

        for key, button in self._tabs.items():
            button.clicked.connect(lambda _=False, k=key: self._on_tab(k))
        self.retranslate()
        self._apply_state()

    # ---- state ----

    def _on_tab(self, key):
        pages = {"jobs": self.jobs, "results": self.result_table if self.result_model.rows else self.results, "logs": self.logs}
        same_page = self.stack.currentWidget() is pages[key]
        self.stack.setCurrentWidget(pages[key])
        self.toggle.setChecked(self._collapsed or not same_page)

    def _on_toggle(self, checked):
        self._collapsed = not checked
        self._apply_state()

    def _apply_state(self):
        expanded = not self._collapsed
        self.stack.setVisible(expanded)
        if self._collapsed:
            self.setFixedHeight(COLLAPSED_HEIGHT)
        else:
            self.setMinimumHeight(EXPANDED_MIN)
            self.setMaximumHeight(220)
            self.resize(self.width(), 200)
        parent = self.parentWidget()
        if isinstance(parent, QSplitter):
            height = 200 if expanded else COLLAPSED_HEIGHT
            parent.setSizes([max(0, parent.height() - height - parent.handleWidth()), height])
        zh = self.translator.language == "zh"
        self.toggle.setIcon(icon("chevron-up" if self._collapsed else "chevron-down", QtTheme().muted))
        self.toggle.setToolTip(
            ("展开面板" if self._collapsed else "收起面板") if zh
            else ("Expand panel" if self._collapsed else "Collapse panel"))

    @property
    def is_collapsed(self):
        return self._collapsed

    def expand(self):
        self.toggle.setChecked(True)

    def collapse(self):
        self.toggle.setChecked(False)

    # ---- content ----

    def set_status(self, text, role="neutral"):
        self.status.set_status(text, role)

    def set_jobs(self, text):
        self.update_job(dict(id='single_prediction', type='Prediction', status='FAILED' if 'failed' in text.lower() or '失败' in text else ('SUCCESS' if 'SUCCESS' in text or '成功' in text else 'RUNNING'), progress='—', elapsed=text))

    def update_job(self, job):
        rows = list(self.jobs_model.rows)
        existing = next((i for i, row in enumerate(rows) if row.get('id') == job['id']), None)
        if existing is None:
            rows.insert(0, job)
        else:
            rows[existing] = job
        self.jobs_model.replace(rows[:100])

    def set_batch_results(self, report):
        self.result_kind = "batch"
        self.result_model.replace([row.to_output_dict() for row in report.rows])


    def set_results(self, text):
        self.result_kind = "prediction"
        self.result_model.replace([])
        rows=[]
        for line in text.splitlines():
            label,separator,value=line.partition(": ")
            rows.append((label,value) if separator else ("",line))
        self.results.set_sections([(ux("result",self.translator.language=="zh"),rows)],zh=self.translator.language=="zh")
        if self._tabs["results"].isChecked():
            self.stack.setCurrentWidget(self.results)

    def append_log(self, text):
        self.logs.appendPlainText(text)

    def clear_results(self):
        self.result_kind = None
        self.results.clear()
        self.result_model.replace([])

    def retranslate(self):
        zh = self.translator.language == "zh"
        self.jobs.retranslate(zh)
        self.jobs_model.display_values={'type':{'Prediction':'单次预测' if zh else 'Prediction','Batch':'批量预测' if zh else 'Batch','Training':'训练' if zh else 'Training','Validation':'验证' if zh else 'Validation'}}
        self.result_table.retranslate(zh)
        self.jobs_model.headers = {key:qt_text('activity_'+key,zh) for key in self.jobs_model.columns}
        self.jobs_model.headerDataChanged.emit(Qt.Horizontal,0,len(self.jobs_model.columns)-1)
        tabs = (("任务", "结果", "日志") if zh else ("Jobs", "Results", "Logs"))
        for key, text in zip(self._tabs, tabs, strict=False):
            self._tabs[key].setText(text)

        self.results.setPlaceholderText("暂无预测结果" if zh else "No prediction results")
        self._apply_state()
