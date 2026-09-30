from damage_gui.qt.widgets.workspace import DetailView, WorkspaceHeader, ux

"""Validation presentation, reusing core reports and the scientific comparison view."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from damage_gui.model.validation import VALIDATION_MODES
from damage_gui.qt.i18n import qt_text, trace_label, training_stage, validation_text
from damage_gui.qt.validation_workflow import clean
from damage_gui.qt.widgets.field_view import FieldView
from damage_gui.qt.workflow import table


class ValidationWorkspace(QWidget):
    export_message=Signal(str,str)
    def __init__(self,translator,controller):
        super().__init__()
        self.translator,self.controller=translator,controller
        self.bundle=None
        self.result=None
        self.config=None
        self.compatible=False
        self._probe_token=0
        self.probe_error=""
        self.setObjectName('batchWorkspace')
        self.setAttribute(Qt.WA_StyledBackground,True)
        root=QVBoxLayout(self)
        self.header=WorkspaceHeader();self.title=self.header.title;self.model_label=self.header.context
        root.addWidget(self.header)
        self.status=QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.tabs=QTabWidget()
        root.addWidget(self.tabs,1)
        self.overview=QWidget()
        layout=QVBoxLayout(self.overview)
        self.summary=DetailView(dark=True)
        self.summary.setObjectName('validationSummary')
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary)
        self.tabs.addTab(self.overview,'')
        self.samples,self.sample_model=table(('h','v','deg','confidence','MeanRelativeError (%)','P95HybridError (%)','CentroidError (m)','PeakPositionError (m)','PeakIntensityError','IoU','Dice'),dark=True)
        self.sample_page=QWidget();sample_layout=QVBoxLayout(self.sample_page);sample_layout.setContentsMargins(0,0,0,0)
        tools=QHBoxLayout();self.search=QLineEdit();self.search.textChanged.connect(self.sample_model.filter);tools.addWidget(self.search)
        self.sort_buttons=[]
        for column,key in ((5,'P95'),(4,'MRE'),(10,'Dice')):
            button=QPushButton(key);button.clicked.connect(lambda _,col=column:self.samples.sortByColumn(col,Qt.AscendingOrder if col==10 else Qt.DescendingOrder));tools.addWidget(button);self.sort_buttons.append(button)
        sample_layout.addLayout(tools);sample_layout.addWidget(self.samples)
        self.tabs.addTab(self.sample_page,'')
        self.comparison=FieldView()
        self.comparison_page=QWidget()
        comparison_layout=QVBoxLayout(self.comparison_page)
        comparison_layout.setContentsMargins(0,0,0,0)
        self.sample_caption=QLabel()
        self.sample_caption.setWordWrap(True)
        self.sample_caption.setContentsMargins(10,4,10,4)
        comparison_layout.addWidget(self.sample_caption)
        comparison_layout.addWidget(self.comparison,1)
        self.tabs.addTab(self.comparison_page,'')
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        self.histogram_figure=Figure()
        self.histogram=FigureCanvasQTAgg(self.histogram_figure)
        self.tabs.addTab(self.histogram,'')
        self.samples.doubleClicked.connect(self.open_sample)
        self.samples.clicked.connect(self.open_sample)
        self.inspector=QWidget()
        controls=QVBoxLayout(self.inspector)
        controls.setContentsMargins(14,14,14,14)
        self.mode=QComboBox()
        for mode in VALIDATION_MODES:
            self.mode.addItem(mode,mode)
        self.layer=QComboBox()
        self.seed=QSpinBox()
        self.seed.setRange(0,2147483647)
        self.seed.setValue(42)
        self.test_size=QDoubleSpinBox()
        self.test_size.setRange(.01,.99)
        self.test_size.setValue(.2)
        self.corner_v=QDoubleSpinBox()
        self.corner_v.setRange(0,10000)
        self.corner_deg=QDoubleSpinBox()
        self.corner_deg.setRange(0,180)
        self.data_edit=QLineEdit()
        self.browse=QPushButton('…')
        self.browse.clicked.connect(self._browse)
        self.metric_view=QComboBox()
        self.metric_view.addItem('Raw','raw')
        self.metric_view.addItem('Smoothed','smoothed')
        self.labels={}
        for key,widget in (('data',self.data_edit),('mode',self.mode),('layer',self.layer),('seed',self.seed),('test_size',self.test_size),('corner_v',self.corner_v),('corner_deg',self.corner_deg),('metric_view',self.metric_view)):
            label=QLabel()
            self.labels[key]=label
            controls.addWidget(label)
            controls.addWidget(widget)
            if key=='data':
                controls.addWidget(self.browse)
        self.help=QLabel()
        self.help.setWordWrap(True)
        self.help.setProperty('role','secondary')
        controls.addWidget(self.help)
        self.run_button=QPushButton()
        self.run_button.setProperty('role','primary')
        self.cancel_button=QPushButton()
        self.export_button=QPushButton()
        for button in (self.run_button,self.cancel_button,self.export_button):
            controls.addWidget(button)
        controls.addStretch()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.layer.currentIndexChanged.connect(self._check)
        for widget in (self.seed,self.test_size,self.corner_v,self.corner_deg):
            widget.valueChanged.connect(self._check)
        self.data_edit.textChanged.connect(self._discover)
        self.metric_view.currentIndexChanged.connect(self.render)
        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(controller.cancel)
        self.export_button.clicked.connect(self.export)
        controller.job_changed.connect(self._job_changed)
        controller.finished.connect(self._finished)
        translator.subscribe(self.retranslate)
        self.retranslate()
        self._controls()

    def text(self,key):
        return validation_text(key,self.translator.language=='zh')

    def retranslate(self):
        self.title.setText(self.text('title'))
        self.search.setPlaceholderText('搜索样本' if self.translator.language=='zh' else 'Search samples')
        zh=self.translator.language=='zh'
        self.samples.retranslate(zh)
        self.sample_model.headers={key:trace_label(key.split(' (')[0],zh)+(' (%)' if '(%)' in key else ' (m)' if '(m)' in key and key.startswith('Centroid') is False and key.startswith('PeakPosition') is False else '') for key in self.sample_model.columns}
        self.sample_model.headerDataChanged.emit(Qt.Horizontal,0,len(self.sample_model.columns)-1)
        for key,label in self.labels.items():
            label.setText(self.text(key))
        for i,mode in enumerate(VALIDATION_MODES):
            self.mode.setItemText(i,self.text(mode))
        for i,key in enumerate(('raw','smoothed')):
            self.metric_view.setItemText(i,self.text(key))
        for i,key in enumerate(('overview','samples','comparison','distribution')):
            self.tabs.setTabText(i,self.text(key))
        for button,key in ((self.run_button,'run'),(self.cancel_button,'cancel'),(self.export_button,'export')):
            button.setText(self.text(key))
        self._mode_changed()
        self.comparison.retranslate(self.translator.language=='zh')
        self.comparison.load_button.hide()
        if not self.comparison._has_result:
            self.comparison.empty_title.setText(self.text('comparison'))
            self.comparison.empty_body.setText(self.text('select_sample'))
        if self.result is not None:
            self._status_text(self.controller.job,self.controller.state)
            if hasattr(self,'selected_sample'):
                self._sample_caption(self.selected_sample)
        self.render()

    def set_bundle(self,bundle):
        self.bundle=bundle
        model_id=bundle.metadata.model_id if bundle.metadata else 'legacy'
        self.model_label.setText(f'{bundle.level} · {getattr(bundle.model,"model_name",bundle.model_type)} · {model_id[:10]}…')
        self.model_label.setToolTip(model_id)
        config=bundle.resolved_config()
        self.seed.setValue(config.random_state)
        self.test_size.setValue(config.test_size)
        self.corner_v.setValue(config.corner_v_min)
        self.corner_deg.setValue(config.corner_deg_min)
        self.data_edit.setText(bundle.data_dir or '')
        self._discover()
        self._controls()

    def _browse(self):
        path=QFileDialog.getExistingDirectory(self,self.text('data'))
        if path:
            self.data_edit.setText(path)

    def _discover(self,*_):
        if self.bundle is None:
            return
        path=self.data_edit.text()
        self.records=[]
        self.compatible=False
        self._controls()
        if not path:
            self._mode_changed()
            self.status.setText(self.text('unavailable'))
            return
        token=path
        level=self.bundle.level
        def work(context):
            from damage_gui.data.loader import DamageDataManager
            return DamageDataManager(path).get_level_records(level) if path and Path(path).is_dir() else []
        def done(event):
            if token!=self.data_edit.text():
                return
            self.records=event.result if event.status.value=='SUCCESS' else []
            if not self.records:
                self.status.setText(self.text('unavailable'))
            self._mode_changed()
        self.controller.workflow._submit_read('validation_data',work,done)

    def _mode_changed(self,*_):
        mode=self.mode.currentData()
        field={'leave_h_out':'h','leave_v_out':'v','leave_deg_out':'deg'}.get(mode)
        selected=self.layer.currentData()
        self.layer.blockSignals(True)
        self.layer.clear()
        self.layer.addItem(self.text('all_layers'),None)
        if field:
            for value in sorted({getattr(record.condition,field) for record in getattr(self,'records',[])}):
                self.layer.addItem(f'{field} = {value:g}',value)
            index=self.layer.findData(selected)
            if index>=0:
                self.layer.setCurrentIndex(index)
        self.layer.blockSignals(False)
        for key,widget,visible in (('layer',self.layer,bool(field)),('seed',self.seed,mode=='random'),('test_size',self.test_size,mode=='random'),('corner_v',self.corner_v,mode=='corner'),('corner_deg',self.corner_deg,mode=='corner')):
            widget.setVisible(visible)
            self.labels[key].setVisible(visible)
        self._check()
        self.help.setText(self.text('random_help' if mode=='random' else 'corner_help' if mode=='corner' else 'layer_help')+'\n'+self.text('retrain'))
        self._controls()

    def _check(self,*_):
        self.compatible=False
        self._probe_token+=1
        token=self._probe_token
        records=getattr(self,'records',[])
        if not records or self.bundle is None or self.bundle.model_type not in ('rbf','pod_rbf'):
            self._controls()
            return
        import dataclasses
        config=dataclasses.replace(self.bundle.resolved_config(), model_type=self.bundle.model_type,
                                   random_state=self.seed.value(), test_size=self.test_size.value(),
                                   corner_v_min=self.corner_v.value(),corner_deg_min=self.corner_deg.value())
        mode,layer=self.mode.currentData(),self.layer.currentData()
        def work(context):
            from damage_gui.services.validation_service import ValidationService
            return ValidationService.validate_configuration(records,config,mode,layer)
        def done(event):
            if token!=self._probe_token:
                return
            self.compatible=event.status.value=='SUCCESS'
            self.probe_error=event.error_summary or ''
            self._controls()
        self.controller.workflow._submit_read('validation_compatibility',work,done)

    def _controls(self):
        busy=self.controller.workflow.scientific_busy
        available=self.bundle is not None and self.bundle.model_type in ('rbf','pod_rbf') and len(getattr(self,'records',[]))>=5 and self.compatible
        self.run_button.setEnabled(available and not busy)
        self.run_button.setToolTip('' if available else self.probe_error or self.text('unavailable'))
        self.cancel_button.setEnabled(self.controller.running)
        for widget in (self.mode,self.layer,self.seed,self.test_size,self.corner_v,self.corner_deg,self.data_edit,self.browse):
            widget.setEnabled(not busy)
        self.export_button.setEnabled(self.result is not None)

    def run(self):
        if not self.run_button.isEnabled():
            return
        settings=dict(random_state=self.seed.value(),test_size=self.test_size.value(),corner_v_min=self.corner_v.value(),corner_deg_min=self.corner_deg.value())
        self.result=None
        self.summary.setPlainText(self.text("running"))
        self.sample_model.replace([])
        self.comparison.clear()
        self.comparison.load_button.hide()
        self.comparison.empty_title.setText(self.text("comparison"))
        self.comparison.empty_body.setText(self.text("select_sample"))
        self.sample_caption.clear()
        self.tabs.setCurrentIndex(0)
        self.config=__import__('dataclasses').replace(self.bundle.resolved_config(),**settings)
        self.controller.run(self.bundle,self.data_edit.text(),self.mode.currentData(),settings,self.layer.currentData(),self.metric_view.currentData())

    def _job_changed(self,job):
        self.header.set_status(job["status"])
        self._controls()
        if job['status'] in ('PENDING','RUNNING'):
            stage=training_stage(job.get('stage') or '',self.translator.language=='zh')
            self.status.setText(f'{self.text("running")} {job["progress"]} · {job["elapsed"]}\n{stage}')

    def _finished(self,completion):
        job,self.result,state=completion
        self._status_text(job,state)
        self.render()
        self._controls()

    def _status_text(self,job,state):
        self.status.setText(f'{self.text("complete") if job["status"]=="SUCCESS" else self.text("failed") if job["status"]=="FAILED" else self.text("cancelled")} · {self.text(state["payload"]["validation_mode"])} · {job["elapsed"]}' + ('\n'+str(job.get('error') or '') if job['status']=='FAILED' else '') + ('' if state['persisted'] else '\n'+qt_text('history_write_failed',self.translator.language=='zh')))

    def render(self,*_):
        if self.result is None:
            job=self.controller.job
            key='ready' if not job else 'failed' if job['status']=='FAILED' else 'cancelled' if job['status']=='CANCELLED' else 'running' if self.controller.running else 'ready'
            self.summary.setPlainText(self.text(key)+('\n'+str(job.get('error') or '') if job and job['status']=='FAILED' else ''))
            return
        view=self.metric_view.currentData()
        threshold=self.config.relative_error_threshold
        scope=f'damage_gt_{threshold:.2f}'
        numerical=next((row for row in self.result.accuracy if row.get('field')==view and row.get('scope')==scope),{})
        spatial=next((row for row in self.result.accuracy if row.get('scope')=='spatial'),{})
        from collections import Counter
        zh=self.translator.language=='zh'
        sections=[]
        entries=[(self.text('metric_view'),self.text(view)),(ux('scope',zh),scope)]
        for key in ('R2','MeanRelativeError','P95HybridError','RMSE','MAE'):
            value=clean(numerical.get(key))
            entries.append((trace_label(key,zh),'—' if value is None else f'{value:.2%}' if key in ('MeanRelativeError','P95HybridError') else f'{value:.6g}'))
        sections.append((self.text('numerical'),entries))
        entries=[]
        for key in ('CentroidError','PeakPositionError','PeakIntensityError','IoU','Dice'):
            value=clean(spatial.get(key));entries.append((trace_label(key,zh),f'{value:.6g}' if value is not None else None))
        sections.append((self.text('spatial'),entries))
        counts=Counter(row['confidence'] for row in self.result.samples)
        sections.append((self.text('reliability'),[(confidence,counts[confidence]) for confidence in ('HIGH','MEDIUM','LOW')]+[(self.text('outside'),sum(row['outside_global_support'] for row in self.result.samples)),(self.text('local'),sum(row['local_support_insufficient'] for row in self.result.samples))]))
        payload=self.controller.state['payload'];parameters=payload['parameters'];mode=payload['validation_mode']
        entries=[(self.text('mode'),self.text(mode)),(ux('samples',zh),len(self.result.samples))]
        if mode=='random':entries.extend([(self.text('seed'),parameters['random_state']),(self.text('test_size'),parameters['test_size'])])
        if mode=='corner':entries.extend([(self.text('corner_v'),parameters['corner_v_min']),(self.text('corner_deg'),parameters['corner_deg_min'])])
        for fold in self.result.folds:entries.append((fold['label'],f"{fold['train']} / {fold['test']}"))
        sections.append((ux('execution',zh),entries))
        self.summary.set_sections(sections,advanced=payload,zh=zh)
        suffix=f'_gt_{threshold:.2f}'
        rows=[]
        for record in self.result.samples:
            row=dict(record)
            for display,key in (('MeanRelativeError (%)','MeanRelativeError'),('P95HybridError (%)','P95HybridError')):
                value=record.get(('Raw'+key if view=='raw' else key)+suffix)
                row[display]=value*100 if value is not None else None
            for key in ('CentroidError','PeakPositionError','PeakIntensityError','IoU','Dice'):
                row[key+' (m)' if key in ('CentroidError','PeakPositionError') else key]=record.get('Spat_'+key)
            rows.append(row)
        self.sample_model.replace(rows)
        self._histogram(numerical,rows)

    def _histogram(self,numerical,rows):
        import math

        from damage_gui.visualization.theme import DARK_SCIENTIFIC as theme
        figure=self.histogram_figure
        figure.clear()
        figure.set_facecolor(theme.background)
        axis=figure.add_subplot(111)
        axis.set_facecolor(theme.background)
        values=[row["P95HybridError (%)"] for row in rows if row.get("P95HybridError (%)") is not None and math.isfinite(row["P95HybridError (%)"])]
        if values:
            axis.hist(values,bins=min(10,len(values)),color="#86a9df",edgecolor=theme.background)
        p95=clean(numerical.get("P95HybridError"))
        if p95 is not None:
            axis.axvline(p95*100,color=theme.error_warm,label=self.text("hist_p95"),linewidth=1)
            legend=axis.legend(facecolor=theme.background,edgecolor=theme.edge)
            for label in legend.get_texts(): label.set_color(theme.label)
        axis.set_title("误差分布" if self.translator.language=="zh" else "Error Distribution",color=theme.title)
        axis.set_xlabel(self.text("hist_x"),color=theme.label)
        axis.set_ylabel(self.text("hist_y"),color=theme.label)
        axis.tick_params(colors=theme.tick)
        for spine in axis.spines.values(): spine.set_color(theme.edge)
        figure.tight_layout()
        self.histogram.draw_idle()

    def open_sample(self,index):
        if not index.isValid() or self.result is None:
            return
        sample=self.sample_model.rows[index.row()]
        self.selected_sample=sample
        self._sample_caption(sample)
        truth,prediction=self.result.fields[sample['sample_id']]
        from damage_gui.visualization.plots import render_heatmaps
        self.comparison.show_figure(render_heatmaps(truth,prediction,config=self.config,display_threshold=self.config.display_threshold))
        self.comparison.retranslate(self.translator.language=='zh')
        self.tabs.setCurrentIndex(2)

    def _sample_caption(self,sample):
        suffix=f'_gt_{self.config.relative_error_threshold:.2f}'
        def percentage(key):
            value=clean(sample.get(key))
            return '—' if value is None else f'{value:.2%}'
        values=[f"{sample['level']} / h={sample['h']:g} m / v={sample['v']:g} m/s / θ={sample['deg']:g}° / {sample['confidence']}",
                f"Raw MeanRE {percentage('RawMeanRelativeError'+suffix)} · P95 {percentage('RawP95HybridError'+suffix)} / Smoothed MeanRE {percentage('MeanRelativeError'+suffix)} · P95 {percentage('P95HybridError'+suffix)}"]
        for key in ('CentroidError','PeakPositionError','PeakIntensityError','IoU','Dice'):
            value=clean(sample.get('Spat_'+key))
            values.append(f'{trace_label(key,self.translator.language=="zh")}: '+('—' if value is None else f'{value:.5g}')+(' m' if key in ('CentroidError','PeakPositionError') else ''))
        self.sample_caption.setText(values[0]+'\n'+values[1]+'\n'+' · '.join(values[2:]))

    def restore_settings(self, values):
        parameters=values.get('parameters') or {}
        self.mode.setCurrentIndex(self.mode.findData(values['validation_mode']))
        for key,widget in (('random_state',self.seed),('test_size',self.test_size),('corner_v_min',self.corner_v),('corner_deg_min',self.corner_deg)):
            if parameters.get(key) is not None:
                widget.setValue(parameters[key])
        index=self.layer.findData(parameters.get('held_out_value'))
        if index>=0:
            self.layer.setCurrentIndex(index)
        self.metric_view.setCurrentIndex(self.metric_view.findData(values.get('metric_view','raw')))

    def export(self):
        if self.result is None:
            return
        path,_=QFileDialog.getSaveFileName(self,self.text('export'),'validation_summary.json','JSON (*.json)')
        if path:
            Path(path).write_text(json.dumps(clean(self.controller.state['payload']),ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
            from damage_gui.qt.widgets.workspace import ux
            self.export_message.emit(ux('exported',self.translator.language=='zh')+' · '+Path(path).name,'ok')
