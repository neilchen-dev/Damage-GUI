from damage_gui.qt.widgets.workspace import DetailView, EmptyState, WorkspaceHeader, ux

"""Model registry table and fact-only metadata inspector."""
import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from damage_gui.qt.i18n import trace_label, training_text, validation_text
from damage_gui.qt.workflow import details, table
from damage_gui.services.model_registry_service import ModelRegistryService


class ModelRegistryWorkspace(QWidget):
    train_requested = Signal()
    operation_changed = Signal(bool)
    activated = Signal(object)
    history_requested = Signal(object)
    load_requested = Signal()
    message = Signal(str)
    registered = Signal(str)

    def __init__(self,translator,workflow):
        super().__init__()
        self.translator,self.workflow=translator,workflow
        self.rows=[];self.current_bundle=None;self.current_path='';self.current_id=None
        self.selected=None;self.info=None;self._token=0;self._operation=False;self.last_elapsed={}
        root=QVBoxLayout(self)
        self.header=WorkspaceHeader();self.title=self.header.title;self.context=self.header.context;root.addWidget(self.header)
        bar=QHBoxLayout();self.level=QComboBox();self.level.addItem('', '');self.level.addItems(['F','M','P'])
        self.status=QComboBox()
        for value in ('','ACTIVE','AVAILABLE','LEGACY','MISSING','ARCHIVED'):self.status.addItem(value,value)
        self.search=QLineEdit();self.refresh_button=QPushButton();self.load_button=QPushButton()
        for widget in (self.level,self.status,self.search,self.refresh_button,self.load_button):bar.addWidget(widget)
        root.addLayout(bar)
        self.table,self.model=table(('model_id','level','model_type','app_version','created_at','status','training_data_hash'),dark=True)
        root.addWidget(self.table,1)
        self.empty=EmptyState(callback=lambda:self.train_requested.emit());root.addWidget(self.empty,1);self.empty.hide()
        self.note=QLabel();self.note.setWordWrap(True);root.addWidget(self.note)
        self.inspector=QWidget();dock=QVBoxLayout(self.inspector)
        self.detail=DetailView();self.detail.setReadOnly(True);dock.addWidget(self.detail)
        self.activate_button,self.register_button,self.related_button,self.validation_button=[QPushButton() for _ in range(4)]
        for widget in (self.activate_button,self.register_button,self.related_button,self.validation_button):dock.addWidget(widget)
        self.refresh_button.clicked.connect(self.refresh);self.load_button.clicked.connect(self.load_requested)
        for widget in (self.level,self.status):widget.currentIndexChanged.connect(self._filter)
        self.search.textChanged.connect(self._filter)
        self.table.selectionModel().currentRowChanged.connect(self._select)
        self.activate_button.clicked.connect(self.activate)
        self.register_button.clicked.connect(lambda:self.register(self.current_bundle) if self.current_bundle else None)
        self.related_button.clicked.connect(lambda:self.history_requested.emit(dict(model_id=self.selected['model_id'])) if self.selected else None)
        self.validation_button.clicked.connect(self.open_validation)
        translator.subscribe(self.retranslate);self.retranslate()

    def t(self,key):return training_text(key,self.translator.language=='zh')

    def service(self):return ModelRegistryService(self.workflow.db_path)

    def set_current(self,bundle,path):
        self.current_bundle,self.current_path=bundle,path
        meta=getattr(bundle,'metadata',None);self.current_id=meta.model_id if meta else None
        self.refresh()

    def refresh(self):
        self._token+=1;token=self._token;started=time.perf_counter()
        def done(event):
            if token!=self._token:return
            self.last_elapsed['registry_workflow_elapsed']=time.perf_counter()-started
            if event.status.value=='SUCCESS':
                self.rows,elapsed=event.result
                self.last_elapsed['registry_load']=elapsed
                self._filter()
            else:self.note.setText(event.error_summary or self.t('trace_failed'))
        def load(context):
            started=time.perf_counter()
            rows=self.service().list_models()
            return rows,time.perf_counter()-started
        self.workflow._submit_read('registry_list',load,done)

    def _filter(self,*_):
        selected_id=self.selected.get('model_id') if self.selected else None
        rows=[dict(row) for row in self.rows]
        if self.current_bundle and not any(row['model_id']==self.current_id for row in rows):
            bundle=self.current_bundle;meta=getattr(bundle,'metadata',None)
            row=dict(model_id=self.current_id or '—',level=bundle.level,model_type=bundle.model_type,
                     app_version=meta.app_version if meta else None,created_at=meta.created_at if meta else None,
                     status='UNREGISTERED' if meta else 'LEGACY',path=self.current_path,
                     training_data_hash=meta.training_data_hash if meta else None,external=True)
            if meta:row.update(parameters_json=json.dumps(meta.parameters),code_commit=meta.code_commit,
                               training_samples=meta.training_samples)
            rows.append(row)
        level=self.level.currentText() if self.level.currentIndex() else ''
        status=self.status.currentData();query=self.search.text().lower()
        rows=[row for row in rows if (not level or row['level']==level) and (not status or row['status']==status) and query in row['model_id'].lower()]
        self.context.setText(ux('model_count',self.translator.language=='zh').format(count=len(rows),active=sum(row.get('status')=='ACTIVE' for row in rows)))
        self.model.replace(rows)
        self.empty.setVisible(not rows);self.table.setVisible(bool(rows))
        self.selected=None;self.info=None;self.detail.clear();self._controls()
        if rows:
            index=next((i for i,row in enumerate(rows) if row['model_id']==selected_id),0)
            self.table.setCurrentIndex(self.model.index(index,0))

    def _select(self,index,*_):
        if not index.isValid():return
        self.header.set_status(self.model.rows[index.row()]["status"])
        self.selected=dict(self.model.rows[index.row()]);row=self.selected;self.info=None;self._controls()
        if row.get('external'):
            path=Path(row['path']) if row['path'] else None
            self.info=dict(row,exists=bool(path and path.is_file()),size=path.stat().st_size if path and path.is_file() else None,training_jobs=[],latest_validation=None)
            self._render();return
        def done(event):
            if not self.selected or self.selected['model_id']!=row['model_id']:return
            if event.status.value=='SUCCESS':self.info=event.result;self._render()
            else:self.detail.setPlainText(event.error_summary or self.t('trace_failed'))
        self.workflow._submit_read('registry_detail',lambda context:self.service().detail(row),done)

    def _render(self):
        info=self.info
        if not info:return
        zh=self.translator.language=='zh'
        current=(info['model_id']==self.current_id and self.current_bundle is not None) or (info.get('external') and self.current_bundle is not None and getattr(self.current_bundle,'metadata',None) is None)
        sections=[(ux('model',zh),[(self.t('model_id'),info.get('model_id')),(self.t('level'),info.get('level')),(self.t('type'),str(info.get('model_type','—')).upper().replace('_','-')),(self.t('status'),info.get('status')),(self.t('created'),info.get('created_at')),(self.t('current_app'),ux('yes' if current else 'no',zh))]),
            (ux('provenance',zh),[(self.t('software'),info.get('app_version')),(self.t('commit'),info.get('code_commit')),(self.t('hash'),info.get('training_data_hash'))])]
        training=[(self.t('samples'),info.get('training_samples'))]
        for job in info.get('training_jobs',[]):
            training.append((self.t('training_job'),job['id']))
            training.append((self.t('dataset'),details(job).get('dataset') or job.get('input_source')))
        sections.append((ux('training',zh),training))
        validation=info.get('latest_validation');metrics=[]
        if validation:
            payload=details(validation)
            metrics.append((self.t('validation_history'),validation_text(payload.get('validation_mode','title'),zh)))
            selected=next((row for row in payload.get('accuracy',[]) if row.get('field')=='raw' and row.get('scope')==payload.get('metric_scope')), {})
            for key in ('R2','MeanRelativeError','P95HybridError'):
                value=selected.get(key)
                metrics.append(('Raw '+trace_label(key,zh),f'{value:.2%}' if key!='R2' and isinstance(value,(int,float)) else value))
        else:metrics.append(('',self.t('not_validated')))
        sections.append((ux('validation',zh),metrics))
        sections.append((ux('artifact',zh),[(self.t('path'),info.get('path')),(self.t('exists'),ux('yes' if info.get('exists') else 'no',zh)),(self.t('size'),info.get('size'))]))
        if info['status']=='LEGACY':sections.insert(0,('',[('',self.t('legacy'))]))
        self.detail.set_sections(sections,advanced=info,zh=zh)
        self.detail.setToolTip(info.get('path',''))
        self._controls()

    def _controls(self):
        busy=self.workflow.scientific_busy or self._operation
        row=self.selected or {}
        self.activate_button.setEnabled(not busy and bool(row) and not row.get('external') and row.get('status') not in ('MISSING','ARCHIVED'))
        self.activate_button.setToolTip(self.t('busy') if busy else self.t('available_note'))
        self.register_button.setEnabled(not busy and bool(self.current_bundle and getattr(self.current_bundle,'metadata',None)) and not any(row['model_id']==self.current_id for row in self.rows))
        self.related_button.setEnabled(bool(row) and not row.get('external'))
        self.validation_button.setEnabled(bool(self.info and self.info.get('latest_validation')))
        self.load_button.setEnabled(not busy)

    def _set_operation(self, value):
        self._operation=value
        self.workflow.model_operation=value
        self.operation_changed.emit(value)
        self._controls()

    def register(self,bundle):
        if self._operation or self.workflow.scientific_busy:return
        self._set_operation(True);started=time.perf_counter()
        def done(event):
            self._set_operation(False);self.last_elapsed['registration_workflow_elapsed']=time.perf_counter()-started
            if event.status.value=='SUCCESS':
                self.last_elapsed['model_save']=event.result['save_seconds']
                self.registered.emit(event.result['model_id']);self.message.emit(self.t('registered'));self.workflow.history_changed.emit();self.refresh()
            else:self.message.emit(event.error_summary or self.t('trace_failed'))
            self._controls()
        self.workflow._submit_read('model_register',lambda context:self.service().register(bundle),done)

    def activate(self):
        if not self.activate_button.isEnabled():return
        row=dict(self.selected);self._set_operation(True)
        def done(event):
            self._set_operation(False)
            if event.status.value=='SUCCESS':self.activated.emit(event.result);self.refresh()
            else:self.message.emit(event.error_summary or self.t('trace_failed'))
            self._controls()
        self.workflow._submit_read('model_activate',lambda context:self.service().activate(row),done)

    def open_validation(self):
        job=self.info.get('latest_validation') if self.info else None
        if job:self.history_requested.emit(dict(model_id=self.selected['model_id'],kind='validation',job_id=job['id']))

    def retranslate(self):
        self.empty.title.setText(ux('no_models',self.translator.language=='zh'));self.empty.description.setText(ux('begin',self.translator.language=='zh'));self.empty.button.setText(self.t('training'));self.empty.button.show()
        self.table.retranslate(self.translator.language=='zh')
        self.title.setText(self.t('models'));self.level.setItemText(0,self.t('all'));self.status.setItemText(0,self.t('all'))
        for i in range(1,self.status.count()):self.status.setItemText(i,self.t(self.status.itemData(i)))
        self.search.setPlaceholderText(self.t('search'));self.note.setText(self.t('available_note'))
        for widget,key in [(self.refresh_button,'refresh'),(self.load_button,'load'),(self.activate_button,'activate'),(self.register_button,'register'),(self.related_button,'related'),(self.validation_button,'validation_history')]:widget.setText(self.t(key))
        self.model.headers=dict(zip(self.model.columns,[self.t('model_id'),self.t('level'),self.t('type'),self.t('software'),self.t('created'),self.t('status'),self.t('hash')], strict=False))
        self.model.display_values={'status':{value:self.t(value) for value in ('ACTIVE','AVAILABLE','LEGACY','MISSING','ARCHIVED','UNREGISTERED')},'model_type':{'rbf':'RBF','pod_rbf':'POD-RBF'}}
        if self.model.rows:self.model.dataChanged.emit(self.model.index(0,0),self.model.index(len(self.model.rows)-1,len(self.model.columns)-1))
        self.model.headerDataChanged.emit(Qt.Horizontal,0,len(self.model.columns)-1)
        self._render();self._controls()
