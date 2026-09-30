"""Qt main window — CAE-style workbench shell.

Structure::

    Application Bar   menus · current model · language
    Tool Rail         56 px icon navigation
    Workspace         page header · dark scientific viewport
    Inspector         INPUT / RESULT / MODEL for the active workspace
    Activity Panel    Jobs / Results / Logs dock with status readout

Business wiring is unchanged: PredictionPanel drives
PredictionService / model registry / OOD; TaskAdapter drives TaskManager;
this class only arranges presentation.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from damage_gui.qt.i18n import Translator, qt_text, trace_label
from damage_gui.qt.panels.batch import BatchWorkspace
from damage_gui.qt.panels.history import HistoryWorkspace
from damage_gui.qt.panels.model_registry import ModelRegistryWorkspace
from damage_gui.qt.panels.prediction import PredictionPanel
from damage_gui.qt.panels.training import TrainingWorkspace
from damage_gui.qt.panels.validation import ValidationWorkspace
from damage_gui.qt.task_adapter import TaskAdapter
from damage_gui.qt.training_workflow import TrainingWorkflow
from damage_gui.qt.validation_workflow import ValidationWorkflow
from damage_gui.qt.widgets.activity_panel import ActivityPanel
from damage_gui.qt.widgets.field_view import FieldView
from damage_gui.qt.widgets.tool_rail import ToolRail
from damage_gui.qt.workflow import Workflow


class DamageQtMainWindow(QMainWindow):
    def __init__(self, task_adapter=None):
        super().__init__()
        self.setWindowTitle('DamageLab')
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        self.task_adapter = task_adapter or TaskAdapter()
        self.translator = Translator()
        self.workflow = Workflow(self.task_adapter, parent=self)
        self.workflow.validation = ValidationWorkflow(self.workflow)
        self.workflow.training = TrainingWorkflow(self.workflow)

        self._close_after_prediction = False
        self._pages = {}
        self._build()
        self._desktop_actions()
        self._navigate('prediction')
        self.translator.subscribe(self._retranslate)
        self._retranslate()

    # ---------- construction ----------

    def _build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(root)

        # -- Application bar --
        self._actions()
        top = QWidget()
        top.setObjectName('appbar')
        top.setFixedHeight(42)
        bar = QHBoxLayout(top)
        bar.setContentsMargins(14, 0, 10, 0)
        bar.setSpacing(10)
        brand = QLabel('DamageLab')
        brand.setProperty('role', 'app-name')
        bar.addWidget(brand)
        self.menubar = QMenuBar()
        self._build_menus()
        bar.addWidget(self.menubar)
        bar.addStretch()
        self.top_model = QLabel('No model loaded')
        self.top_model.setProperty('role', 'secondary')
        bar.addWidget(self.top_model)
        self.language_button = QPushButton('中文')
        self.language_button.clicked.connect(self._toggle_language)
        bar.addWidget(self.language_button)
        outer.addWidget(top)

        # -- Body: tool rail · workspace+activity · inspector --
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.rail = ToolRail(self.translator)
        self.rail.navigation_requested.connect(self._navigate)
        body.addWidget(self.rail)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.pages = QStackedWidget()
        self._build_pages()
        self.splitter.addWidget(self.pages)
        self._activity = ActivityPanel(self.translator)
        self.splitter.addWidget(self._activity)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([700, 34])
        body.addWidget(self.splitter, 1)

        # -- Inspector dock --
        self.inspector = QStackedWidget()
        self.inspector.setObjectName('inspectorDock')
        self.inspector.setFixedWidth(280)
        self._prediction_panel = PredictionPanel(self.translator)
        self._prediction_panel.bind_workflow(self.workflow)
        self.inspector.addWidget(self._prediction_panel)
        placeholder = QWidget()
        pl = QVBoxLayout(placeholder)
        pl.setContentsMargins(14, 14, 14, 14)
        self.inspector_note = QLabel()
        self.inspector_note.setProperty('role', 'secondary')
        self.inspector_note.setWordWrap(True)
        pl.addSpacing(6)
        pl.addWidget(self.inspector_note)
        pl.addStretch()
        self.inspector.addWidget(placeholder)
        self.inspector.addWidget(self.batch_workspace.inspector)
        self.inspector.addWidget(self.history_workspace.inspector)
        self.inspector.addWidget(self.validation_workspace.inspector)
        self.inspector.addWidget(self.training_workspace.inspector)
        self.inspector.addWidget(self.registry_workspace.inspector)
        body.addWidget(self.inspector)
        outer.addLayout(body, 1)

        from damage_gui.qt.widgets.workspace import scroll_inspector
        for widget in (self._prediction_panel,self.batch_workspace.inspector,self.validation_workspace.inspector,self.history_workspace.inspector,self.registry_workspace.inspector):
            scroll_inspector(widget)
        self._connect()
        import logging

        from damage_gui.qt.log_bridge import QtLogHandler
        self._log_handler = QtLogHandler(self._activity)
        logging.getLogger('damage_gui').addHandler(self._log_handler)

    def _actions(self):
        self._act_open = QAction(self)
        self._act_open.setShortcut(QKeySequence.Open)
        self._act_open.triggered.connect(self._prediction_open)
        self._act_save = QAction(self)
        self._act_save.setShortcut(QKeySequence.Save)
        self._act_save.setEnabled(False)
        self._act_save.triggered.connect(self._prediction_panel_save)
        self._act_quit = QAction(self)
        self._act_quit.setShortcut(QKeySequence.Quit)
        self._act_quit.triggered.connect(self.close)
        self._act_details = QAction(self)
        self._act_details.setEnabled(False)
        self._act_details.triggered.connect(self._show_model_details)
        self._act_run = QAction(self)
        self._act_run.setShortcut(QKeySequence('F5'))
        self._act_run.triggered.connect(self._prediction_run)
        self._act_reset = QAction(self)
        self._act_reset.triggered.connect(lambda: self._field_view.buttons['Reset'].click())
        self._act_pan = QAction(self)
        self._act_pan.setCheckable(True)
        self._act_zoom = QAction(self)
        self._act_zoom.setCheckable(True)
        self._act_probe = QAction(self)
        self._act_probe.setCheckable(True)
        self._act_export = QAction(self)
        self._act_export.triggered.connect(lambda: self._field_view.buttons['Export'].click())
        for action in (self._act_open, self._act_save, self._act_quit, self._act_run):
            self.addAction(action)

    def _build_menus(self):
        self._menus = {}
        for key in ('file', 'model', 'analysis', 'view', 'help'):
            self._menus[key] = self.menubar.addMenu('')
        self._menus['file'].addAction(self._act_open)
        self._menus['file'].addAction(self._act_save)
        self._menus['file'].addSeparator()
        self._menus['file'].addAction(self._act_quit)
        self._menus['model'].addAction(self._act_details)
        self._menus['analysis'].addAction(self._act_run)
        self._menus['view'].addAction(self._act_reset)
        self._menus['view'].addAction(self._act_pan)
        self._menus['view'].addAction(self._act_zoom)
        self._menus['view'].addAction(self._act_probe)
        self._menus['view'].addSeparator()
        self._menus['view'].addAction(self._act_export)
        self._act_about = QAction(self)
        self._act_about.triggered.connect(self._show_about)
        self._menus['help'].addAction(self._act_about)

    def _build_pages(self):
        # Prediction: page header above the dark scientific viewport.
        page = QWidget()
        page.setObjectName('workspacePage')
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        from damage_gui.qt.widgets.workspace import WorkspaceHeader
        header=WorkspaceHeader();header.setContentsMargins(16,8,16,0)
        self.prediction_header=header
        self.page_title=header.title;self.page_meta=header.context
        col.addWidget(header)
        self._field_view = FieldView()
        col.addWidget(self._field_view, 1)
        self.pages.addWidget(page)
        self._pages['prediction'] = page

        self.batch_workspace = BatchWorkspace(self.translator, self.workflow)
        self.history_workspace = HistoryWorkspace(self.translator, self.workflow)
        self.validation_workspace = ValidationWorkspace(self.translator, self.workflow.validation)
        self.training_workspace = TrainingWorkspace(self.translator, self.workflow)
        self.registry_workspace = ModelRegistryWorkspace(self.translator, self.workflow)
        for key, workspace in (('training',self.training_workspace),('models',self.registry_workspace),('batch',self.batch_workspace),('history',self.history_workspace),('validation',self.validation_workspace)):
            self.pages.addWidget(workspace)
            self._pages[key] = workspace

        self._placeholder_glyphs = {}
        for key, _glyph, title, chinese, note in (
            ('aim', '⊕', 'Aim', '瞄准优化', 'Aim optimization arrives in a later phase.'),
            ('settings', '⚙', 'Settings', '设置', 'Application settings arrive in a later phase.'),
        ):
            holder = QWidget()
            center = QVBoxLayout(holder)
            center.addStretch()
            from damage_gui.qt.icons import icon as outline_icon
            from damage_gui.qt.theme import QtTheme
            icon = QLabel()
            icon.setPixmap(outline_icon(key, QtTheme().faint, 24).pixmap(24, 24))
            icon.setAlignment(Qt.AlignCenter)
            label = QLabel(title)
            label.setAlignment(Qt.AlignCenter)
            label.setProperty('role', 'page-title')
            body = QLabel(note)
            body.setAlignment(Qt.AlignCenter)
            body.setProperty('role', 'secondary')
            center.addWidget(icon)
            center.addWidget(label)
            center.addWidget(body)
            center.addStretch()
            self.pages.addWidget(holder)
            self._pages[key] = holder
            self._placeholder_glyphs[key] = (label, body, title, chinese, note)

    def _connect(self):
        panel = self._prediction_panel
        panel.prediction_completed.connect(self._on_prediction_completed)
        panel.model_loaded.connect(self._on_model_loaded)
        panel.running_changed.connect(self._on_running_changed)
        panel.prediction_failed.connect(self._on_prediction_failed)
        panel.status_message.connect(self._show_status)
        panel.error_raised.connect(lambda text: self._activity.append_log(text))
        self.workflow.job_changed.connect(self._activity.update_job)
        self.workflow.prediction_job_changed.connect(self._activity.update_job)
        self.workflow.prediction_finished.connect(self._trace_completion)
        self.workflow.prediction_job_changed.connect(lambda _: self.batch_workspace._controls())
        self.workflow.job_changed.connect(lambda _: self._on_running_changed(self._prediction_panel.is_running))
        self.history_workspace.restore_requested.connect(self._restore_prediction_inputs)
        self.workflow.completed.connect(self._batch_completed)
        self.workflow.validation.job_changed.connect(self._activity.update_job)
        self.workflow.validation.job_changed.connect(lambda _: self._on_running_changed(self._prediction_panel.is_running))
        self.workflow.validation.finished.connect(self._validation_completed)
        self.workflow.prediction_job_changed.connect(lambda _: self.validation_workspace._controls())
        self.workflow.job_changed.connect(lambda _: self.validation_workspace._controls())
        self.workflow.training.job_changed.connect(self._activity.update_job)
        self.workflow.training.job_changed.connect(lambda _: self._on_running_changed(self._prediction_panel.is_running))
        self.workflow.training.finished.connect(self._training_completed)
        self.training_workspace.register_requested.connect(self.registry_workspace.register)
        self.training_workspace.validate_requested.connect(self._validate_draft)
        self.registry_workspace.operation_changed.connect(lambda _:self._on_running_changed(self._prediction_panel.is_running))
        self.registry_workspace.registered.connect(self.training_workspace.mark_registered)
        self.registry_workspace.activated.connect(lambda result: self._prediction_panel._bind_bundle(*result))
        self.registry_workspace.train_requested.connect(lambda:self._navigate('training'))
        self.registry_workspace.load_requested.connect(self._prediction_open)
        self.registry_workspace.history_requested.connect(self._model_history)
        self.registry_workspace.message.connect(lambda text:self._show_status(text,'warning'))
        self._activity.jobs.doubleClicked.connect(self._open_session_job)
        self._field_view.export_message.connect(self._show_status)
        self.validation_workspace.export_message.connect(self._show_status)
        self.validation_workspace.comparison.export_message.connect(self._show_status)
        self._field_view.load_requested.connect(self._prediction_open)
        # Keep View menu toggles in sync with the viewport toolbar buttons.
        toggles = (('Pan', self._act_pan), ('Zoom', self._act_zoom),
                   ('Probe', self._act_probe))
        for key, action in toggles:
            action.triggered.connect(lambda _=False, k=key: self._field_view.buttons[k].click())
            self._field_view.buttons[key].toggled.connect(action.setChecked)

    # ---------- navigation ----------

    def _navigate(self, key):
        if key not in self._pages:
            return
        self.pages.setCurrentWidget(self._pages[key])
        self.rail.set_current(key)
        self.inspector.setCurrentIndex({'prediction':0,'batch':2,'history':3,'validation':4,'training':5,'models':6}.get(key,1))
        self._update_commands()
        if key == 'history':
            self.history_workspace.refresh()
        if key == 'models':
            self.registry_workspace.refresh()

    # ---------- model / prediction actions ----------

    def _prediction_open(self):
        self._prediction_panel._on_load_model()

    def _prediction_panel_save(self):
        self._prediction_panel._on_save_model()

    def _prediction_run(self):
        self._prediction_panel._on_predict()

    def _show_model_details(self):
        bundle = self._prediction_panel.bundle
        if bundle is None:
            return
        name = getattr(bundle.model, 'model_name', type(bundle.model).__name__)
        meta = getattr(bundle, 'metadata', None)
        model_id = meta.model_id if meta else self.translator.t('model.legacy')
        lines = [
            f'Level: {bundle.level}',
            f'Type: {name}',
            f'Model ID: {model_id}',
            f'Validation: {bundle.validation_mode}',
            f'Samples: {len(bundle.train_conditions)} train / {len(bundle.test_conditions)} test',
            f'Train time: {bundle.train_time_seconds:.1f} s',
            f'Path: {self._prediction_panel.model_path_edit.text()}',
        ]
        QMessageBox.information(self, 'Model', '\n'.join(lines))

    def _on_model_loaded(self, bundle):
        name = getattr(bundle.model, 'model_name', type(bundle.model).__name__)
        self._act_save.setEnabled(True)
        self._act_details.setEnabled(True)
        self.top_model.setText(f'{bundle.level} · {name}')
        self._field_view.export_model_name = f'{bundle.level}_{name}'
        self.registry_workspace.set_current(bundle, self._prediction_panel.model_path_edit.text())
        self.batch_workspace.set_bundle(bundle)
        self.validation_workspace.set_bundle(bundle)
        self._update_model_header()
        self._activity.clear_results()
        self._activity.retranslate()
        self._field_view._loaded = True
        self._field_view.clear()
        self._field_view.retranslate(self.translator.language == 'zh')
        self._show_status(f'Model loaded: {name}', 'ok')
        self._navigate('prediction')
        self._on_running_changed(False)

    def _update_model_header(self):
        panel = self._prediction_panel
        bundle = panel.bundle
        if bundle is None:
            return
        zh = self.translator.language == 'zh'
        name = getattr(bundle.model, 'model_name', type(bundle.model).__name__)
        meta = getattr(bundle, 'metadata', None)
        model_id = meta.model_id if meta else self.translator.t('model.legacy')
        short_id = model_id if len(model_id) <= 12 else model_id[:10] + '…'
        self.page_meta.setText(f'{bundle.level} · {name} · {short_id}')
        self.page_meta.setToolTip(model_id)
        lines = [panel.model_meta_plain]
        if meta:
            lines.extend([
                f"{'软件版本' if zh else 'App version'}: {meta.app_version}",
                f"{'创建时间' if zh else 'Created'}: {meta.created_at}",
                f"{'训练工况' if zh else 'Training samples'}: {meta.training_samples}",
            ])
        lines.append(f"{'验证方式' if zh else 'Validation'}: {bundle.validation_mode}")
        self.top_model.setToolTip('\n'.join(lines))

    def _on_prediction_completed(self, result):
        self.prediction_header.set_status("SUCCESS")
        from damage_gui.visualization.plots import render_heatmaps
        bundle = self._prediction_panel.bundle
        config = bundle.resolved_config() if bundle else None
        figure = render_heatmaps(result.truth, result.prediction,
                                 display_threshold=config.display_threshold if config else 0.08,
                                 config=config)
        self._field_view.show_figure(figure)

        self._update_prediction_results(result)

    def _update_prediction_results(self, result):
        bundle = self._prediction_panel.bundle
        details = [qt_text('prediction_detail', self.translator.language == 'zh'),
                   f"{trace_label('id', self.translator.language == 'zh')}: {self.workflow.prediction_job['id'] if self.workflow.prediction_job else '—'}",
                   self._prediction_panel.reliability_label.text()]
        state = getattr(self.workflow, '_prediction_state', None)
        if state and not state['persisted']:
            details.append(qt_text('persistence_failed', self.translator.language == 'zh'))
        if bundle:
            n_train = len(bundle.train_conditions)
            n_test = len(bundle.test_conditions)
            details.extend([f'Validation: {bundle.validation_mode}',
                            f'Samples: {n_train} train / {n_test} test',
                            f'Train time: {bundle.train_time_seconds:.1f} s',
                            self._prediction_panel.model_meta_plain])
        if result.truth_comparison_metrics:
            details.extend(f'{key}: {value}'
                           for key, value in result.truth_comparison_metrics.items())
        details[:0] = [f"{bundle.level if bundle else '—'} / h={result.condition.h:g} / v={result.condition.v:g} / θ={result.condition.deg:g}",
                       f"{qt_text('maximum', self.translator.language == 'zh')}: {result.peak_intensity:.6f}",
                       f"{qt_text('area', self.translator.language == 'zh')}: {result.damage_area_ratio:.2%}",
                       f"{qt_text('confidence', self.translator.language == 'zh')}: {result.ood_report.level.upper() if result.ood_report else '—'}"]
        self._activity.set_results('\n'.join(details))

    def _on_running_changed(self, running):
        if running:self.prediction_header.set_status("RUNNING")
        if self._field_view._running != running:
            self._field_view.set_running(running)
        if not running and self._close_after_prediction:
            self._close_after_prediction = False
            QTimer.singleShot(0, self.close)
        self._update_commands()
        self._prediction_panel.predict_button.setEnabled(not running and not self.workflow.scientific_busy and self._prediction_panel.bundle is not None)
        self._prediction_panel.load_button.setEnabled(not self.workflow.scientific_busy)
        self._prediction_panel.save_button.setEnabled(not self.workflow.scientific_busy and self._prediction_panel.bundle is not None)
        self.training_workspace._controls()
        self.registry_workspace._controls()
        self.batch_workspace._controls()
        self.validation_workspace._controls()
        for action in (self._act_open, self._act_run, self._act_save):
            action.setEnabled(not running and not self.workflow.scientific_busy and (action is self._act_open or
                                               self._prediction_panel.bundle is not None))
        for action in (self._act_reset, self._act_pan, self._act_zoom,
                       self._act_probe, self._act_export):
            action.setEnabled(self._field_view._has_result and not running)

    def _trace_completion(self, completion):
        job, state = completion
        if job['status'] != 'SUCCESS':
            self._activity.set_results(f"{qt_text('prediction_detail', self.translator.language == 'zh')} · {job['status']}\n{job['detail']}\n{job.get('error') or '—'}")

    def _on_prediction_failed(self, message):
        self.prediction_header.set_status("FAILED")
        self._field_view.show_error()

    def _training_completed(self, completion):
        job, result, state = completion
        self._activity.set_results(self.training_workspace.summary.toPlainText())
        self._activity.result_kind = 'training'
        from damage_gui.qt.i18n import training_text
        self._show_status(f'{training_text("training",self.translator.language=="zh")} · {job["status"]}', 'ok' if job['status']=='SUCCESS' and state['persisted'] else 'warning')
        self._on_running_changed(self._prediction_panel.is_running)

    def _validate_draft(self, bundle):
        if self.workflow.scientific_busy:
            return
        # Bind only the validation target; current prediction model stays selected.
        self.validation_workspace.set_bundle(bundle)
        self._navigate('validation')

    def _model_history(self, values):
        self.history_workspace.model_filter.setText(values['model_id'])
        if values.get('kind'):
            self.history_workspace.kind.setCurrentIndex(self.history_workspace.kind.findData(values['kind']))
        self._navigate('history')
        if values.get('job_id'):
            self.history_workspace.selected_id=values['job_id']
            self.workflow.load_detail(values['job_id'])

    def _validation_completed(self, completion):
        job, result, state = completion
        self._activity.result_kind = 'validation'
        self._activity.set_results(self.validation_workspace.summary.toPlainText())
        self._activity.result_kind = 'validation'
        self._show_status(f'Validation · {job["status"]}' if state['persisted'] else qt_text('history_write_failed',self.translator.language=='zh'), 'ok' if job['status']=='SUCCESS' and state['persisted'] else 'warning')
        self.batch_workspace._controls()

    def _restore_prediction_inputs(self, values):
        panel = self._prediction_panel
        if self.workflow.scientific_busy:
            self._show_status(qt_text('shared_model_busy', self.translator.language == 'zh'), 'warning')
            return
        if values.get('validation_mode'):
            self.validation_workspace.restore_settings(values)
            self._navigate('validation')
            return
        for key, spin in (('h',panel.h_spin),('v',panel.v_spin),('deg',panel.deg_spin)):
            if values.get(key) is not None:
                spin.setValue(float(values[key]))
        if values.get('level'):
            panel.level_combo.setCurrentText(values['level'])
        self._navigate('prediction')

    def _open_session_job(self, index):
        if not index.isValid():
            return
        job = self._activity.jobs_model.rows[index.row()]
        self._navigate('history')
        self.history_workspace.selected_id = job['id']
        self.workflow.load_detail(job['id'])

    def _batch_completed(self, result):
        job, report = result
        if report:
            self._activity.set_batch_results(report)
        self._show_status(f'Batch: {job["status"]}', 'ok' if job['status'] == 'SUCCESS' else 'warning')

    def _show_status(self, text, role='info'):
        self._activity.set_status(text, role)
        self._activity.append_log(text)

    # ---------- language ----------

    def _show_about(self):
        import platform

        from PySide6 import __version__ as qt_version

        from damage_gui import __version__ as app_version

        zh = self.translator.language == 'zh'
        body = (
            f'DamageLab {app_version}\n\n'
            + ('基于质心对齐 POD-RBF 的毁伤场快速预测工作台。'
               if zh else
               'Centroid-aligned POD-RBF workbench for fast damage-field prediction.')
            + f'\n\nQt {qt_version} · Python {platform.python_version()}\n'
        )
        QMessageBox.about(self, 'DamageLab', body)

    def _toggle_language(self):
        self.translator.set_language('zh' if self.translator.language == 'en' else 'en')

    def _retranslate(self):
        zh = self.translator.language == 'zh'
        self.language_button.setText('中文' if zh else 'EN')
        menus = (('file', '文件', 'File'), ('model', '模型', 'Model'),
                 ('analysis', '分析', 'Analysis'), ('view', '视图', 'View'),
                 ('help', '帮助', 'Help'))
        for key, chinese, english in menus:
            self._menus[key].setTitle(chinese if zh else english)
        self._act_about.setText('关于 DamageLab' if zh else 'About DamageLab')
        actions = (
            (self._act_open, '打开模型…', 'Open Model…'),
            (self._act_save, '保存模型…', 'Save Model…'),
            (self._act_quit, '退出', 'Quit'),
            (self._act_details, '模型详情…', 'Model Details…'),
            (self._act_run, '运行预测', 'Run Prediction'),
            (self._act_reset, '重置视图', 'Reset View'),
            (self._act_pan, '平移', 'Pan'),
            (self._act_zoom, '缩放', 'Zoom'),
            (self._act_probe, '探针', 'Probe'),
            (self._act_export, '导出图像…', 'Export Figure…'),
        )
        for action, chinese, english in actions:
            action.setText(chinese if zh else english)
        self._on_running_changed(self._prediction_panel.is_running)
        self.rail.retranslate()
        self._field_view.retranslate(zh)
        self._prediction_panel.retranslate()
        self._update_model_header()
        self._activity.retranslate()
        if self._activity.result_kind == 'training':
            self._activity.set_results(self.training_workspace.summary.toPlainText())
            self._activity.result_kind = 'training'
        if self._activity.result_kind == 'prediction' and self.workflow.prediction_job:
            if self.workflow.prediction_job['status'] == 'SUCCESS' and self._prediction_panel.current_result:
                self._update_prediction_results(self._prediction_panel.current_result)
            elif self.workflow.prediction_job['status'] in ('FAILED','CANCELLED'):
                self._trace_completion((self.workflow.prediction_job,self.workflow._prediction_state))
        if self._prediction_panel.is_running:
            self._activity.set_status(self.translator.t('status.running'), 'busy')
        elif self._field_view._failed:
            self._activity.set_status(qt_text('failed', zh), 'error')
        elif self._prediction_panel.current_result is not None:
            result = self._prediction_panel.current_result
            state = self.workflow._prediction_state if self.workflow.prediction_job else None
            if state and not state['persisted']:
                self._activity.set_status(qt_text('persistence_failed', zh), 'warning')
            else:
                self._activity.set_status(f"{self.translator.t('status.complete')} — {result.elapsed_ms} ms", 'ok')
        else:
            self._activity.set_status(qt_text('ready', zh), 'neutral')
        self.page_title.setText('预测' if zh else 'Prediction')
        if self._prediction_panel.bundle is None:
            self.page_meta.setText('尚未加载模型' if zh else 'No model loaded')
            self.top_model.setText('尚未加载模型' if zh else 'No model loaded')
        for _, (label, body, title, chinese, note) in self._placeholder_glyphs.items():
            label.setText(chinese if zh else title)
            body.setText('该工作区将在后续阶段开放。' if zh else note)
        if self._activity.result_kind == 'training' and self.workflow.training.job:
            from damage_gui.qt.i18n import training_text
            job=self.workflow.training.job
            self._activity.set_status(f'{training_text("training",zh)} · {job["status"]}', 'ok' if job['status']=='SUCCESS' else 'warning')
        if hasattr(self,'_act_current_run'):
            self._translate_desktop_actions()
        self.inspector_note.setText('此工作区将在后续阶段开放。' if zh
                                    else 'This workspace opens in a later phase.')

    def _desktop_actions(self):
        self._desktop=[]
        def action(name,key,callback,shortcut=None):
            item=QAction(self);item.triggered.connect(callback)
            if shortcut:item.setShortcut(QKeySequence(shortcut))
            self.addAction(item);setattr(self,name,item);self._desktop.append((item,key));return item
        action('_act_current_run','run',self._run_current,'Ctrl+R' if __import__('sys').platform!='darwin' else 'Meta+R')
        action('_act_search','search',self._search_current,'Ctrl+F' if __import__('sys').platform!='darwin' else 'Meta+F')
        action('_act_current_export','exported',self._export_current,'Ctrl+E' if __import__('sys').platform!='darwin' else 'Meta+E')
        action('_act_logs','logs',self._toggle_logs,'Ctrl+L' if __import__('sys').platform!='darwin' else 'Meta+L')
        self._menus['view'].addSeparator()
        for name,key,callback in [('_act_inspector','inspect',lambda:self.inspector.setVisible(not self.inspector.isVisible())),('_act_activity','activity',lambda:self._activity.toggle.click()),('_act_layout','reset',self._reset_layout)]:
            self._menus['view'].addAction(action(name,key,callback))
        self._menus['view'].addAction(self._act_logs)
        self._menus['analysis'].addAction(self._act_current_run)
        self._menus['file'].insertAction(self._act_quit,self._act_current_export)
        self._menus['file'].removeAction(self._act_open)
        self._menus['model'].insertAction(self._act_details,self._act_open)
        self._dataset_action=QAction(self);self._dataset_action.triggered.connect(self._open_dataset)
        self._batch_file_action=QAction(self);self._batch_file_action.triggered.connect(self._open_batch_csv)
        self._menus['file'].insertAction(self._act_current_export,self._dataset_action)
        self._menus['file'].insertAction(self._act_current_export,self._batch_file_action)
        registry=QAction(self);registry.triggered.connect(lambda:self._navigate('models'));self._menus['model'].addAction(registry)
        self._registry_action=registry
        self._command_timer=QTimer(self);self._command_timer.setInterval(150);self._command_timer.timeout.connect(self._update_commands);self._command_timer.start()
        self._translate_desktop_actions();self._update_commands()

    def _translate_desktop_actions(self):
        from damage_gui.qt.widgets.workspace import ux
        zh=self.translator.language=='zh'
        for action,key in self._desktop:action.setText(ux(key,zh))
        self._act_current_export.setText('导出当前视图…' if zh else 'Export Current View…')
        self._dataset_action.setText('打开数据集…' if zh else 'Open Dataset…')
        self._batch_file_action.setText('打开批量 CSV…' if zh else 'Open Batch CSV…')
        self._registry_action.setText('模型库…' if zh else 'Model Registry…')

    def _open_dataset(self):
        if self.workflow.scientific_busy:return
        self._navigate('training');self.training_workspace.browse()

    def _open_batch_csv(self):
        if self.workflow.scientific_busy:return
        self._navigate('batch');self.batch_workspace._browse_csv()

    def _current_key(self):
        return next((key for key,page in self._pages.items() if page is self.pages.currentWidget()),'')

    def _run_button(self):
        return {'prediction':self._prediction_panel.predict_button,'batch':self.batch_workspace.run_button,'validation':self.validation_workspace.run_button,'training':self.training_workspace.run_button}.get(self._current_key())

    def _update_commands(self):
        if not hasattr(self,'_act_current_run'):return
        button=self._run_button()
        self._act_current_run.setEnabled(button is not None and button.isEnabled() and not self.workflow.scientific_busy)
        key=self._current_key()
        self._act_search.setEnabled(key in ('models','history','batch','validation'))
        self._act_current_export.setEnabled((key=='prediction' and self._field_view._has_result) or (key=='validation' and self.validation_workspace.export_button.isEnabled()))

    def _run_current(self):
        button=self._run_button()
        if button and button.isEnabled():button.click()

    def _search_current(self):
        key=self._current_key()
        target={'models':self.registry_workspace.search,'history':self.history_workspace.model_filter,'batch':self.batch_workspace.search,'validation':self.validation_workspace.search}.get(key)
        if key=='validation':self.validation_workspace.tabs.setCurrentIndex(1)
        if target:target.setFocus()
        if hasattr(target,'selectAll') and key in ('models','history'):target.selectAll()

    def _export_current(self):
        key=self._current_key()
        if key=='prediction':self._field_view.buttons['Export'].click()
        elif key=='validation':self.validation_workspace.export()


    def _toggle_logs(self):
        if not self._activity.is_collapsed and self._activity._tabs['logs'].isChecked():self._activity.collapse()
        else:self._activity.expand();self._activity._tabs['logs'].click()

    def _reset_layout(self):
        self.inspector.show();self.rail.show();self._activity.collapse();self.splitter.setSizes([max(0,self.height()-76),34])

    def closeEvent(self, event):
        if self._prediction_panel.is_running:
            self._close_after_prediction = True
            self._activity.set_status(qt_text("closing", self.translator.language == "zh"), "busy")
            event.ignore()
            return
        if self.task_adapter.is_busy():
            if not getattr(self, '_force_close', False):
                zh = self.translator.language == 'zh'
                answer = QMessageBox.question(
                    self,
                    '关闭 DamageLab' if zh else 'Close DamageLab',
                    ('有任务正在运行。关闭应用将终止任务，未完成的工作不会保存。'
                     if zh else
                     'A task is still running. Closing the application will stop '
                     'it; unfinished work is not saved.'),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    event.ignore()
                    return
                self._force_close = True
            self.workflow.cancel()
            self.workflow.validation.cancel()
            self.workflow.training.cancel()
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        self.task_adapter.stop()
        import logging
        logging.getLogger('damage_gui').removeHandler(self._log_handler)
        super().closeEvent(event)
