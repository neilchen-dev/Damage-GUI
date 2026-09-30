from damage_gui.qt.widgets.workspace import DetailView, WorkspaceHeader, ux

"""Training overview and summary; an independent inspector owns configuration."""
import dataclasses

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from damage_gui.config import CONFIG
from damage_gui.qt.i18n import trace_label, training_stage, training_text
from damage_gui.qt.validation_workflow import clean
from damage_gui.services.dataset_service import inspect_dataset


class TrainingSummaryView(DetailView):
    def __init__(self):
        super().__init__(dark=True)


class TrainingInspector(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content.setObjectName("trainingInspectorContent")
        scroll.setObjectName("trainingInspectorScroll")
        layout = QVBoxLayout(content)
        form = QFormLayout()
        self.labels = {}
        self.directory = QLineEdit()
        self.browse, self.inspect = QPushButton(), QPushButton()
        row = QHBoxLayout(); row.addWidget(self.directory); row.addWidget(self.browse)
        self.directory_label = QLabel(); layout.addWidget(self.directory_label); layout.addLayout(row); layout.addWidget(self.inspect)
        self.level = QComboBox(); self.level.addItems(['F', 'M', 'P'])
        self.model_type = QComboBox(); self.model_type.addItem('RBF', 'rbf'); self.model_type.addItem('POD-RBF', 'pod_rbf')
        self.components = QSpinBox(); self.components.setRange(1, 10000); self.components.setValue(CONFIG.pod_n_components)
        for key, widget in [('level',self.level),('type',self.model_type),('components',self.components)]:
            label = QLabel(); self.labels[key]=label; form.addRow(label,widget)
        layout.addLayout(form)
        self.advanced = QGroupBox(); self.advanced.setCheckable(True); self.advanced.setChecked(False)
        self.advanced_body = QWidget(); advanced_form = QFormLayout(self.advanced_body)
        self.kernel = QComboBox(); self.kernel.addItems(['thin_plate_spline','linear','cubic','quintic','multiquadric','inverse_multiquadric','inverse_quadratic','gaussian'])
        self.smoothing = QDoubleSpinBox(); self.smoothing.setRange(0,100); self.smoothing.setDecimals(6)
        self.epsilon = QDoubleSpinBox(); self.epsilon.setRange(0,10000); self.epsilon.setDecimals(6)
        self.seed = QSpinBox(); self.seed.setRange(0,2147483647); self.seed.setValue(CONFIG.random_state)
        self.test_size = QDoubleSpinBox(); self.test_size.setRange(.05,.8); self.test_size.setValue(CONFIG.test_size); self.test_size.setSingleStep(.05)
        self.align = QCheckBox(); self.align.setChecked(CONFIG.align_patterns)
        for key,widget in [('kernel',self.kernel),('smoothing',self.smoothing),('epsilon',self.epsilon),('seed',self.seed),('test_size',self.test_size),('align',self.align)]:
            label=QLabel();self.labels[key]=label;advanced_form.addRow(label,widget)
        box = QVBoxLayout(self.advanced);box.addWidget(self.advanced_body)
        self.advanced.toggled.connect(self.advanced_body.setVisible);self.advanced_body.hide();layout.addWidget(self.advanced)
        self.run_button, self.cancel_button = QPushButton(), QPushButton()
        self.run_button.setProperty('role','primary')
        self.note = QLabel(); self.note.setWordWrap(True); self.note.setProperty('role','secondary')
        layout.addWidget(self.note);layout.addWidget(self.run_button);layout.addWidget(self.cancel_button);layout.addStretch()
        scroll.setWidget(content);outer.addWidget(scroll)


class TrainingWorkspace(QWidget):
    validate_requested = Signal(object)
    register_requested = Signal(object)

    def __init__(self, translator, workflow):
        super().__init__()
        self.translator, self.workflow = translator, workflow
        self.training = workflow.training
        self.base_config = CONFIG
        self.dataset = None
        self._inspection_token = 0
        self.result = None
        self.registered = False
        self.setObjectName('batchWorkspace')
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        self.header=WorkspaceHeader();self.title=self.header.title;self.context=self.header.context
        layout.addWidget(self.header)
        self.tabs = QTabWidget()
        self.overview, self.summary = TrainingSummaryView(), TrainingSummaryView()
        self.figure = Figure(facecolor='#171C23');self.canvas = FigureCanvasQTAgg(self.figure)
        self.tabs.addTab(self.overview,'');self.tabs.addTab(self.summary,'');self.tabs.addTab(self.canvas,'')
        layout.addWidget(self.tabs,1)
        actions=QHBoxLayout();self.validate_button=QPushButton();self.register_button=QPushButton()
        self.validate_button.setProperty("role","empty-action")
        self.register_button.setProperty("role","primary")
        actions.addStretch();actions.addWidget(self.validate_button);actions.addWidget(self.register_button);layout.addLayout(actions)
        self.inspector=TrainingInspector()
        for key in ('directory','level','model_type','components','kernel','smoothing','epsilon','seed','test_size','align','run_button','cancel_button'):
            setattr(self,key,getattr(self.inspector,key))
        self.inspector.browse.clicked.connect(self.browse)
        self.inspector.inspect.clicked.connect(self.inspect)
        self.directory.textChanged.connect(self.invalidate)
        self.level.currentIndexChanged.connect(self._render_dataset)
        self.model_type.currentIndexChanged.connect(self._controls)
        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(self.training.cancel)
        self.validate_button.clicked.connect(lambda:self.validate_requested.emit(self.result.bundle) if self.result else None)
        self.register_button.clicked.connect(lambda:self.register_requested.emit(self.result.bundle) if self.result else None)
        self.training.job_changed.connect(self._job)
        self.training.finished.connect(self._finished)
        translator.subscribe(self.retranslate);self.retranslate()

    def t(self,key):
        return training_text(key,self.translator.language=='zh')

    def browse(self):
        path=QFileDialog.getExistingDirectory(self,self.t('dataset'),self.directory.text())
        if path:
            self.directory.setText(path);self.inspect()

    def invalidate(self,*_):
        self._inspection_token+=1;self.dataset=None;self._render_dataset()

    def inspect(self):
        directory=self.directory.text().strip()
        self.invalidate();token=self._inspection_token
        self.overview.setPlainText('…')
        def finish(event):
            if token!=self._inspection_token:return
            if event.status.value=='SUCCESS':
                self.dataset=event.result;self._render_dataset()
            else:
                self.overview.setPlainText(self.t('inspection_failed')+'\n'+(event.error_summary or ''))
                self._controls()
        self.workflow._submit_read('dataset_inspection',lambda context:inspect_dataset(directory,context.cancel_check),finish)

    def _render_dataset(self,*_):
        zh=self.translator.language=='zh'
        sections=[(ux('dataset',zh),[('',self.t('ready'))])]
        if self.dataset:
            selected=self.dataset['levels'].get(self.level.currentText())
            sections=[(ux('dataset',zh),[(self.t('dataset'),self.dataset['directory']),(self.t('samples'),self.dataset['samples']),(self.t('load_time'),f'{self.dataset["elapsed_seconds"]:.3f} s')]),
                      (self.t('level'),[(level,info['samples']) for level,info in self.dataset['levels'].items()])]
            if selected:
                sections.append((self.t('level')+' · '+self.level.currentText(),[(self.t(key),selected[value]) for key,value in [('samples','samples'),('valid','valid'),('duplicates','duplicates'),('gaps','grid_gaps')]]))
                sections.append((self.t('source_shape'),[(shape,count) for shape,count in selected['shapes'].items()]+[(self.t('target_shape'),f'{self.base_config.target_shape[0]} × {self.base_config.target_shape[1]}')]))
                sections.append((ux('input',zh),[(self.t(key),len(axis)) for key,axis in zip(('heights','velocities','angles'),selected['axes'], strict=False)]))
                if selected['errors']:sections.append((self.t('errors'),[('',error) for error in selected['errors'][:20]]))
            else:sections.append(('',[('',self.t('invalid'))]))
        self.overview.set_sections(sections,advanced=self.dataset,zh=zh);self._controls()

    def _controls(self,*_):
        selected=self.dataset['levels'].get(self.level.currentText()) if self.dataset else None
        valid=bool(selected and selected['valid']>=5 and not selected['errors'] and not selected['duplicates'])
        busy=self.workflow.scientific_busy
        self.run_button.setEnabled(valid and not busy)
        self.run_button.setToolTip(self.t('busy') if busy else ('' if valid else self.t('invalid')))
        self.cancel_button.setEnabled(self.training.running)
        self.components.setEnabled(not busy and self.model_type.currentData()=='pod_rbf')
        for widget in (self.directory,self.level,self.model_type,self.inspector.inspect,self.inspector.browse,self.inspector.advanced):widget.setEnabled(not busy)
        self.validate_button.setEnabled(self.result is not None and not busy)
        self.register_button.setEnabled(self.result is not None and not self.registered and not busy)

    def configuration(self):
        return dataclasses.replace(self.base_config,model_type=self.model_type.currentData(),pod_n_components=self.components.value(),
            rbf_kernel=self.kernel.currentText(),rbf_smoothing=self.smoothing.value(),rbf_epsilon=self.epsilon.value() or None,
            random_state=self.seed.value(),test_size=self.test_size.value(),align_patterns=self.align.isChecked(),validation_mode='random')

    def run(self):
        if not self.run_button.isEnabled():return
        self.result=None;self.registered=False;self.summary.clear();self.figure.clear();self.canvas.draw_idle()
        self.training.run(self.directory.text().strip(),self.level.currentText(),self.configuration())
        self.tabs.setCurrentIndex(1)

    def _job(self,job):
        self.header.set_status(job["status"])
        self.context.setText(f'{job["detail"]} · {job["status"]} · {job["elapsed"]}\n{training_stage(job.get("stage", ""),self.translator.language=="zh")}')
        self._controls()

    def _finished(self,completion):
        job,self.result,state=completion
        self._render_result()
        if not state['persisted']:self.summary.appendPlainText(self.t('trace_failed'))
        self._controls()

    def mark_registered(self,model_id):
        if self.result and self.result.bundle.metadata.model_id==model_id:
            self.registered=True;self._render_result();self._controls()

    def _render_result(self):
        if not self.result:
            job=self.training.job
            self.summary.setPlainText(f'{job["status"]}\n{job.get("error") or ""}' if job else self.t('no_result'))
            return
        bundle=self.result.bundle;meta=bundle.metadata
        zh=self.translator.language=='zh'
        sections=[(self.t('registered' if self.registered else 'unregistered'),[]),
            (ux('model',zh),[(self.t('type'),getattr(bundle.model,'model_name',bundle.model_type)),(self.t('level'),bundle.level),(self.t('output'),meta.model_id)]),
            (ux('dataset',zh),[(self.t('train_count'),len(bundle.train_conditions)),(self.t('test_count'),len(bundle.test_conditions)),(self.t('hash'),meta.training_data_hash)]),
            (ux('execution',zh),[(self.t('duration'),f'{bundle.train_time_seconds:.3f} s'),(self.t('software'),meta.app_version),(self.t('commit'),meta.code_commit)]),
        ]
        metrics=[]
        focus=f'damage_gt_{bundle.resolved_config().relative_error_threshold:.2f}'
        for field in ('raw','smoothed'):
            row=next((row for row in clean(bundle.accuracy_report.to_dict('records')) if row.get('field')==field and row.get('scope')==focus),{})
            for key in ('R2','MeanRelativeError','P95HybridError','RMSE','MAE'):
                value=row.get(key)
                displayed=f'{value:.2%}' if key in ('MeanRelativeError','P95HybridError') and isinstance(value,(int,float)) else (f'{value:.6g}' if isinstance(value,(int,float)) else '—')
                metrics.append((f'{field.title()} {trace_label(key,zh)}',displayed))
        sections.append((ux('holdout',zh),[('',self.t('holdout_note')),(ux('scope',zh),focus)]+metrics))
        self.summary.set_sections(sections,advanced=meta.to_dict(),zh=zh)
        self.figure.clear();axis=self.figure.add_subplot(111);axis.set_facecolor('#171C23')
        pca=getattr(bundle.model,'pca',None)
        if pca is not None:
            ratio=pca.explained_variance_ratio_;axis.plot(np.arange(1,len(ratio)+1),np.cumsum(ratio)*100,color='#72A0E0')
            axis.set_ylabel('%',color='#B5BEC9');axis.set_xlabel(self.t('components'),color='#B5BEC9');axis.set_title(self.t('spectrum'),color='#D8DEE7')
        else:axis.text(.5,.5,self.t('no_spectrum'),ha='center',va='center',transform=axis.transAxes,color='#B5BEC9')
        axis.tick_params(colors='#B5BEC9');self.figure.tight_layout();self.canvas.draw_idle()

    def retranslate(self):
        self.title.setText(self.t('training'))
        for i,key in enumerate(('overview','summary','spectrum')):self.tabs.setTabText(i,self.t(key))
        self.inspector.directory_label.setText(self.t('dataset'))
        for key,label in self.inspector.labels.items():label.setText(self.t(key))
        self.inspector.advanced.setTitle(self.t('advanced'))
        for widget,key in [(self.inspector.browse,'browse'),(self.inspector.inspect,'inspect'),(self.run_button,'run'),(self.cancel_button,'cancel'),(self.validate_button,'validate'),(self.register_button,'register')]:widget.setText(self.t(key))
        self.inspector.note.setText(self.t('holdout_note'));self._render_dataset();self._render_result()
        if self.training.job:self._job(self.training.job)
