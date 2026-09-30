from damage_gui.qt.widgets.workspace import WorkspaceHeader

"""Compact Batch workspace and light input inspector."""
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from damage_gui.qt.i18n import trace_label
from damage_gui.qt.workflow import table


class BatchWorkspace(QWidget):
    def __init__(self, translator, workflow):
        super().__init__()
        self.translator, self.workflow = translator, workflow
        self.bundle = None
        self.parsed = None
        self.input_path = ''
        self.setObjectName('batchWorkspace')
        self.setAttribute(Qt.WA_StyledBackground, True)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        self.header=WorkspaceHeader();self.title=self.header.title;self.model_label=self.header.context
        root.addWidget(self.header)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        for widget in (self.summary, self.progress):
            root.addWidget(widget)
        self.preview, self.preview_model = table(('job_id','h','v','deg','level','status','error'), dark=True)
        self.search=QLineEdit();self.search.setPlaceholderText(self.text('搜索预览','Search preview'))
        self.search.textChanged.connect(self.preview_model.filter)
        root.addWidget(self.search)
        root.addWidget(self.preview, 1)
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.output_label.setTextInteractionFlags(self.output_label.textInteractionFlags() | Qt.TextSelectableByMouse)
        root.addWidget(self.output_label)
        buttons = QHBoxLayout()
        self.open_button = QPushButton()
        self.folder_button = QPushButton()
        self.copy_button = QPushButton()
        self.output = ''
        for button in (self.open_button, self.folder_button, self.copy_button):
            button.setProperty("role", "empty-action")
            buttons.addWidget(button)
            button.setEnabled(False)
        buttons.addStretch()
        root.addLayout(buttons)
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.output)))
        self.folder_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.output).parent))))
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.output))
        self.inspector = QWidget()
        controls = QVBoxLayout(self.inspector)
        controls.setContentsMargins(14, 16, 14, 16)
        self.labels = []
        self.csv_edit, self.truth_edit, self.output_edit = QLineEdit(), QLineEdit(), QLineEdit()
        self.browse_buttons = []
        for edit, callback in ((self.csv_edit, self._browse_csv), (self.truth_edit, self._browse_truth), (self.output_edit, self._browse_output)):
            label = QLabel()
            self.labels.append(label)
            controls.addWidget(label)
            row = QHBoxLayout()
            row.addWidget(edit)
            browse = QPushButton('…')
            browse.setFixedWidth(32)
            browse.clicked.connect(callback)
            row.addWidget(browse)
            self.browse_buttons.append(browse)
            controls.addLayout(row)
        self.validate_button = QPushButton()
        self.run_button = QPushButton()
        self.run_button.setProperty('role', 'primary')
        self.cancel_button = QPushButton()
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setProperty('role', 'secondary')
        for widget in (self.validate_button, self.note, self.run_button, self.cancel_button):
            controls.addWidget(widget)
        controls.addStretch()
        self.csv_edit.textChanged.connect(self._input_changed)
        self.validate_button.clicked.connect(self.validate)
        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(self.cancel)
        workflow.validated.connect(self._validated)
        workflow.validation_failed.connect(self._failed_validation)
        workflow.job_changed.connect(self._job_changed)
        workflow.completed.connect(self._completed)
        translator.subscribe(self.retranslate)
        self.retranslate()
        self._controls()

    def text(self, zh, en):
        return zh if self.translator.language == 'zh' else en

    def retranslate(self):
        self.title.setText(self.text('批量预测', 'Batch Prediction'))
        self.search.setPlaceholderText(self.text('搜索预览','Search preview'))
        zh=self.translator.language=='zh'
        self.preview.retranslate(zh)
        self.preview_model.headers={key:trace_label('id' if key=='job_id' else 'error_summary' if key=='error' else key,zh) for key in self.preview_model.columns}
        self.preview_model.headerDataChanged.emit(Qt.Horizontal,0,len(self.preview_model.columns)-1)
        for label, zh, en in zip(self.labels, ('输入 CSV','真值数据目录（可选）','输出 CSV'), ('Input CSV','Truth directory (optional)','Output CSV'), strict=False):
            label.setText(self.text(zh,en))
        self.output_edit.setPlaceholderText(self.text('自动生成，不覆盖文件','Auto-generated; never overwrite'))
        self.validate_button.setText(self.text('校验输入','Validate'))
        self.run_button.setText(self.text('运行批量预测','Run Batch'))
        self.cancel_button.setText(self.text('取消','Cancel'))
        self.open_button.setText(self.text('打开结果','Open Result'))
        self.folder_button.setText(self.text('打开所在目录','Show in Folder'))
        self.copy_button.setText(self.text('复制路径','Copy Path'))
        self.note.setText(self.text('✓ 逐行错误隔离（后端固定行为）\n只预览前 100 行。', '✓ Continue on error (runner behavior)\nPreview limited to 100 rows.'))
        if self.workflow.report:
            self._completed((self.workflow.job, self.workflow.report))
        elif self.workflow.running:
            self._job_changed(self.workflow.job)
        elif self.parsed:
            self._show_validation()
        else:
            self.summary.setText(self.text('选择 CSV 文件，然后校验输入。','Select a CSV file, then validate input.'))

    def set_bundle(self, bundle):
        self.bundle = bundle
        meta = getattr(bundle, 'metadata', None)
        model_id=meta.model_id if meta else 'legacy'
        self.model_label.setText(f'{bundle.level} · {getattr(bundle.model,"model_name",type(bundle.model).__name__)} · {model_id[:10]}…')
        self.model_label.setToolTip(model_id)
        if not self.workflow.running:
            self._input_changed()
        self._controls()

    def load_csv(self, path):
        self.csv_edit.setText(str(path))

    def _input_changed(self, *_):
        self.parsed = None
        self.workflow.invalidate_validation()
        if not self.workflow.running:
            self.preview_model.replace([])
            self.summary.setText(self.text('输入已更改，请校验。','Input changed; validate before running.'))
        self._controls()

    def _controls(self, validating=False):
        busy = self.workflow.scientific_busy
        for widget in (self.csv_edit, self.truth_edit, self.output_edit, *self.browse_buttons):
            widget.setEnabled(not busy)
        self.validate_button.setEnabled(bool(self.csv_edit.text()) and not busy and not validating)
        self.run_button.setEnabled(self.bundle is not None and self.parsed is not None and not busy)
        self.cancel_button.setEnabled(busy)

    def _browse_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, self.text('选择 CSV','Select CSV'), '', 'CSV (*.csv)')
        if path:
            self.load_csv(path)

    def _browse_truth(self):
        path = QFileDialog.getExistingDirectory(self, self.text('真值数据','Truth data'))
        if path:
            self.truth_edit.setText(path)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, self.text('输出 CSV','Output CSV'), '', 'CSV (*.csv)')
        if path:
            self.output_edit.setText(path)

    def validate(self):
        self.parsed = None
        self._controls(validating=True)
        self.summary.setText(self.text('正在校验…','Validating…'))
        self.workflow.validate(self.csv_edit.text(), self.bundle.level if self.bundle else 'F')

    def _validated(self, result):
        self.parsed, preview, self.input_path = result
        self.preview_model.replace(preview)
        self._show_validation()
        self._controls()

    def _show_validation(self):
        parsed = self.parsed
        errors = '\n'.join(f'Row {row.line_no}: {row.error}' for row in parsed.invalid[:10])
        self.summary.setText(self.text('批量概览','Batch Overview') + f'\nRows {parsed.total}   Valid {len(parsed.rows)}   Invalid {len(parsed.invalid)}\n' + errors)

    def _failed_validation(self, message):
        self.parsed = None
        self.summary.setText(self.text('无法读取 CSV：','Unable to read CSV: ') + message)
        self._controls()

    def run(self):
        if self.bundle is None or self.parsed is None or self.workflow.scientific_busy:
            return
        self.workflow.run(self.bundle, self.parsed, self.input_path, self.output_edit.text(), self.truth_edit.text())

    def cancel(self):
        if self.workflow.cancel():
            self.cancel_button.setEnabled(False)
            self.summary.setText(self.text('正在请求取消；保留已完成结果…','Cancellation requested; preserving completed rows…'))

    def _job_changed(self, job):
        self.header.set_status(job["status"])
        self._controls()
        self.progress.show()
        done, total = (int(value.strip()) for value in job['progress'].split('/'))
        self.progress.setRange(0, max(1,total))
        self.progress.setValue(done)
        if job['status'] in ('PENDING','RUNNING'):
            self.summary.setText(f'{job["status"]} · {done} / {total} · {100*done/max(1,total):.1f}%\nModel ID: {job["model_id"] or "legacy"}\nJob ID: {job["id"]}')

    def _completed(self, result):
        job, report = result
        self._controls()
        if report is None:
            self.summary.setText(self.text('批量执行失败','Batch failed') + '\n' + str(job.get('error') or job['status']))
            return
        counts = Counter(row.ood_level for row in report.rows if row.ood_level)
        self.summary.setText(self.text('批量结果摘要','Batch Summary') + f' · {job["status"]}\nTotal {report.total}   Completed {len(report.rows)}   Succeeded {report.success_count}   Failed {report.failed_count}\n' + '   '.join(f'OOD {key}: {value}' for key,value in sorted(counts.items())) + f'\nElapsed {report.duration_ms/1000:.2f} s\nModel ID: {report.model_id}' + ('' if report.db_recorded else self.text('\n警告：结果未完整写入追溯数据库','\nWarning: results not fully recorded in traceability database')))
        self.output = str(report.output_path or '')
        self.output_label.setText(Path(self.output).name)
        self.output_label.setToolTip(self.output)
        for button in (self.open_button,self.folder_button,self.copy_button):
            button.setEnabled(bool(self.output))
