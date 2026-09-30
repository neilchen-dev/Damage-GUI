from damage_gui.qt.widgets.workspace import DetailView, WorkspaceHeader, ux

"""Repository-backed persistent history with bounded result pages."""
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

from damage_gui.qt.i18n import qt_text, trace_label, training_text, validation_text
from damage_gui.qt.workflow import details, table


class HistoryWorkspace(QWidget):
    restore_requested = Signal(object)
    def __init__(self, translator, workflow):
        super().__init__()
        self.translator, self.workflow = translator, workflow
        self.offset = 0
        self.selected_id = None
        self._detail_data = None
        root = QVBoxLayout(self)
        self.header=WorkspaceHeader();self.title=self.header.title;self.context=self.header.context
        root.addWidget(self.header)
        bar = QHBoxLayout()
        self.kind = QComboBox()
        self.status = QComboBox()
        self.model_filter = QLineEdit()
        self.model_filter.setPlaceholderText("Model ID")
        self.model_filter.setMaximumWidth(260)
        for label, value in (('All',''),('Prediction','prediction'),('Batch','batch_prediction'),('Validation','validation'),('Training','training')):
            self.kind.addItem(label,value)
        for value in ('','PENDING','RUNNING','SUCCESS','FAILED','CANCELLED'):
            self.status.addItem(value or 'All status',value)
        self.refresh_button = QPushButton()
        self.previous = QPushButton('‹')
        self.next = QPushButton('›')
        for widget in (self.kind,self.status,self.model_filter,self.refresh_button,self.previous,self.next):
            bar.addWidget(widget)
        bar.addStretch()
        root.addLayout(bar)
        self.message = QLabel()
        root.addWidget(self.message)
        self.jobs, self.model = table(('created_at','kind','model_id','status','input_source','output','duration_ms'),dark=True)
        root.addWidget(self.jobs,1)
        self.inspector = QWidget()
        dock = QVBoxLayout(self.inspector)
        self.detail = DetailView()
        self.detail.setReadOnly(True)
        dock.addWidget(self.detail)
        self.restore_button = QPushButton()
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore)
        dock.addWidget(self.restore_button)
        self.rows, self.rows_model = table(('row_job_id','level','h','v','deg','status','peak_intensity','error_summary'),dark=True)
        root.addWidget(self.rows,1)
        self.rows.hide()
        self.refresh_button.clicked.connect(self.refresh)
        self.kind.currentIndexChanged.connect(self._filter)
        self.status.currentIndexChanged.connect(self._filter)
        self.model_filter.textChanged.connect(self._filter)
        self.previous.clicked.connect(lambda: self._page(-1000))
        self.next.clicked.connect(lambda: self._page(1000))
        self.jobs.selectionModel().currentRowChanged.connect(self._selected)
        workflow.history_loaded.connect(self._loaded)
        workflow.detail_loaded.connect(self._detail)
        workflow.history_changed.connect(self.refresh)
        translator.subscribe(self.retranslate)
        self.retranslate()

    def retranslate(self):
        zh = self.translator.language == 'zh'
        self.title.setText('历史记录' if zh else 'History')
        self.jobs.retranslate(zh);self.rows.retranslate(zh)
        self.restore_button.setText(qt_text('restore_inputs', zh))
        self.status.setItemText(0,'全部状态' if zh else 'All status')
        self.model.headers = {key:trace_label('output' if key == 'output' else key,zh) for key in self.model.columns}
        self.model.headerDataChanged.emit(Qt.Horizontal,0,len(self.model.columns)-1)
        if self._detail_data:
            self._render_detail()
        self.refresh_button.setText('刷新' if zh else 'Refresh')
        for i,text in enumerate(('全部','单次预测','批量预测','验证','训练') if zh else ('All','Prediction','Batch','Validation','Training')):
            self.kind.setItemText(i,text)
        self.detail.setPlaceholderText('选择任务查看追溯详情' if zh else 'Select a job to inspect traceability')

    def _filter(self,*_):
        self.offset = 0
        self.refresh()

    def _page(self, delta):
        self.offset = max(0,self.offset + delta)
        self.refresh()

    def refresh(self):
        self.message.setText('…')
        self.workflow.load_history(self.kind.currentData(),self.status.currentData(),self.offset,self.model_filter.text().strip())

    def _loaded(self, event):
        if event.status.value != 'SUCCESS':
            self.message.setText(event.error_summary or 'History unavailable')
            return
        rows = event.result
        self.model.replace([dict(row, input_source=self._input_display(row), output=details(row).get('output_model_id') or details(row).get('output_file') or details(row).get('output_csv','')) for row in rows])
        self.message.setText(ux('page',self.translator.language=='zh').format(page=self.offset//1000+1,count=len(rows)))
        self.context.setText(self.message.text())
        self.previous.setEnabled(self.offset > 0)

    def _selected(self,index,*_):
        if index.isValid():
            self.selected_id = self.model.rows[index.row()]['id']
            self.workflow.load_detail(self.selected_id)

    def _detail(self,event):
        if event.status.value != 'SUCCESS':
            self.detail.setPlainText(event.error_summary or 'Detail unavailable')
            return
        job, model, rows = event.result
        if job['id'] != self.selected_id:
            return
        self._detail_data = (job, model, rows)
        self._render_detail()

    def _input_display(self, job):
        info = details(job)
        if job['kind']=='training':
            return f'{info.get("level","—")} · {info.get("model_type","—").upper().replace("_","-")}'
        if job['kind']=='validation':
            mode=info.get('validation_mode') or 'validation'
            from damage_gui.model.validation import VALIDATION_MODES
            label=validation_text(mode,self.translator.language=='zh') if mode in VALIDATION_MODES else mode
            parameters=info.get('parameters') or {}
            field={'leave_h_out':'h','leave_v_out':'v','leave_deg_out':'deg'}.get(mode)
            layer=parameters.get('held_out_value')
            return f'{label} · {field}={layer}' if field and layer is not None else label
        if job['kind'] == 'prediction' and all(key in info for key in ('h','v','deg','level')):
            return f"h={info['h']} / v={info['v']} / θ={info['deg']} / {info['level']}"
        return job.get('input_source') or '—'

    def _restore(self):
        if self._detail_data:
            job, model, rows = self._detail_data
            values = dict(rows[0]) if rows else {}
            values.update(details(job))
            self.restore_requested.emit(values)

    def _render_detail(self):
        job, model, rows = self._detail_data
        zh = self.translator.language == 'zh'
        info = details(job)
        self.header.set_status(job['status'])
        def value(key,item):
            if isinstance(item,float):return f'{item:.2%}' if key in ('damage_area_ratio','MeanRelativeError','P95HybridError') else f'{item:.6g}'
            return item
        sections=[(ux('job',zh),[(trace_label(key,zh),job.get(key)) for key in ('id','kind','status','created_at','duration_ms','error_summary')])]
        inputs=dict(rows[0]) if rows else {};inputs.update(info)
        if job['kind']=='prediction':
            entries=[(trace_label(key,zh),inputs.get(key)) for key in ('level','h','v','deg')]
        elif job['kind']=='validation':
            entries=[(validation_text('mode',zh),self._input_display(job))]
            entries.extend((validation_text({'random_state':'seed','test_size':'test_size','held_out_value':'layer','corner_v_min':'corner_v','corner_deg_min':'corner_deg'}.get(key,key),zh) if key in ('random_state','test_size','held_out_value','corner_v_min','corner_deg_min') else key,val) for key,val in (info.get('parameters') or {}).items())
        elif job['kind']=='training':entries=[(training_text('type' if key=='model_type' else key,zh),info.get(key)) for key in ('dataset','level','model_type')]
        else:entries=[(trace_label('input_source',zh),job.get('input_source'))]
        sections.append((ux('input',zh),entries))
        entries=[]
        if job['kind']=='validation':
            for field in ('raw','smoothed'):
                selected=next((row for row in info.get('accuracy',[]) if row.get('field')==field and row.get('scope')==info.get('metric_scope','overall')), {})
                entries.extend((f'{field.title()} {trace_label(key,zh)}',value(key,selected.get(key))) for key in ('R2','MeanRelativeError','P95HybridError','RMSE','MAE'))
            entries.append(('',validation_text('missing_fields',zh)))
        elif job['kind']=='prediction' and rows:
            entries.extend((trace_label(key,zh),value(key,rows[0].get(key))) for key in ('peak_intensity','damage_area_ratio','ood_level','ood_distance','mean_relative_error','p95_hybrid_error'))
        elif job['kind']=='training':entries=[(training_text('output',zh),info.get('output_model_id')),(training_text('status',zh),info.get('registration')),('',training_text('holdout_note',zh))]
        else:entries=[(trace_label('output',zh),info.get('output_file') or info.get('output_csv'))]
        sections.append((ux('result',zh),entries))
        if model:
            sections.append((ux('model',zh),[(trace_label('model_id' if key=='id' else key,zh),model.get(key)) for key in ('id','model_type','damage_level','training_samples')]))
            path=model.get('artifact_path')
            sections.append((ux('trace',zh),[(trace_label(key,zh),model.get(key)) for key in ('app_version','training_data_hash','code_commit')]+[(trace_label('artifact_path',zh),path if path and Path(path).is_file() else qt_text('model_file_unavailable',zh))]))
        else:sections.append((ux('trace',zh),[('',qt_text('metadata_unavailable',zh))]))
        self.detail.set_sections(sections,advanced={'job':job,'model':model},zh=zh)
        if job['kind']=='validation':
            self.rows_model.columns=('h','v','deg','confidence','Spat_CentroidError','Spat_Dice')
        else:
            self.rows_model.columns=('row_job_id','level','h','v','deg','status','peak_intensity','error_summary')
        self.rows_model.replace(rows or [])
        self.rows.setVisible(bool(rows))
        inputs = details(job) or (rows[0] if rows else {})
        is_validation=job['kind']=='validation' and bool(info.get('validation_mode'))
        self.restore_button.setText(validation_text('restore',zh) if is_validation else qt_text('restore_inputs',zh))
        self.restore_button.setEnabled(is_validation or (job['kind'] == 'prediction' and all(inputs.get(key) is not None for key in ('level','h','v','deg'))))
