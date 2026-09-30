"""Validation job lifecycle and JSON sidecar persistence using existing repositories."""
import dataclasses
import json
import logging
import math
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal

from damage_gui.services.validation_service import ValidationService
from damage_gui.storage.repositories import JobRepository, ModelRepository

logger = logging.getLogger('damage_gui.qt.validation')

def clean(value):
    if isinstance(value, dict):
        return {key:clean(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):
        return [clean(item) for item in value]
    if hasattr(value,'item'):
        value=value.item()
    return None if isinstance(value,float) and not math.isfinite(value) else value

class ValidationWorkflow(QObject):
    job_changed = Signal(object)
    finished = Signal(object)
    def __init__(self, workflow):
        super().__init__(workflow)
        self.workflow=workflow
        self.job=None
        self.result=None
        workflow.adapter.event_received.connect(self._event)

    @property
    def running(self):
        return self.job is not None and self.job['status'] in ('PENDING','RUNNING')

    def run(self,bundle,data_dir,mode,settings,held_out_value=None,metric_view="raw"):
        if self.workflow.scientific_busy:
            return
        job_id=uuid.uuid4().hex
        metadata=getattr(bundle,'metadata',None)
        model_id=metadata.model_id if metadata else None
        db=self.workflow.db_path
        base=bundle.resolved_config()
        config=dataclasses.replace(base,pod_n_components=getattr(bundle.model,'n_components',base.pod_n_components),**settings)
        self.result=None
        self.job=dict(id=job_id,type='Validation',status='PENDING',detail=mode,progress='—',elapsed='—',model_id=model_id)
        payload=dict(job_id=job_id,model_id=model_id,validation_mode=mode,metric_scope=f'damage_gt_{config.relative_error_threshold:.2f}', parameters=dict(settings,held_out_value=held_out_value),
                     data_directory=data_dir, model_type=bundle.model_type, metric_view=metric_view, software_version=metadata.app_version if metadata else None, training_data_hash=metadata.training_data_hash if metadata else None)
        state=dict(result=None,persisted=False,payload=payload)
        self.state=state
        self._started=time.monotonic()
        self.job_changed.emit(dict(self.job))
        def work(context):
            repo=JobRepository(db)
            try:
                db.parent.mkdir(parents=True,exist_ok=True)
            except OSError:
                logger.exception('Unable to create validation traceability directory')
            model_ok=not metadata or ModelRepository(db).upsert_model(metadata)
            recorded=repo.insert_job(kind='validation',job_id=job_id,status='PENDING',model_id=model_id if model_ok else None,
                                     input_source=mode,details=payload)
            started=repo.update_job_state(job_id,status='RUNNING',started_at=datetime.now(timezone.utc).isoformat())
            result=ValidationService().run(bundle,data_dir,config,mode,held_out_value=held_out_value,
                                           progress=context.report_progress,cancel_check=context.cancel_check)
            state['result']=result
            payload.update(accuracy=clean(result.accuracy), sample_count=len(result.samples),folds=clean(result.folds),
                           ood_summary=dict(Counter(row['confidence'] for row in result.samples)),
                           outside_global_support=sum(row['outside_global_support'] for row in result.samples),
                           local_support_insufficient=sum(row['local_support_insufficient'] for row in result.samples))
            try:
                directory=db.parent/'validation_results'
                directory.mkdir(parents=True,exist_ok=True)
                sidecar=directory/f'{job_id}.json'
                with sidecar.open('x',encoding='utf-8') as stream:
                    json.dump(clean(dict(payload,samples=result.samples)),stream,ensure_ascii=False,allow_nan=False,indent=2)
                payload['result_sidecar']=str(sidecar.resolve())
            except OSError:
                logger.exception('Validation sample sidecar persistence failed')
            state['persisted']=bool(model_ok and recorded and started)
            return result
        self._db=db
        self._metadata=metadata
        self.workflow.adapter.submit('validation',work)

    def cancel(self):
        return self.workflow.adapter.cancel('validation')

    def _event(self,event):
        if event.kind!='validation' or self.job is None:
            return
        if event.type!='finished':
            self.job.update(stage=event.stage, status=event.status.value, progress=f'{event.done} / {event.total}' if event.total else '—',
                            elapsed=f'{time.monotonic()-self._started:.1f} s')
            self.job_changed.emit(dict(self.job))
            return
        state=self.state
        self.result=state['result']
        status='CANCELLED' if self.result and self.result.cancelled else event.status.value
        snapshot=dict(self.job,status=status,detail=state['payload']['validation_mode'],elapsed=f'{(event.duration_ms or 0)/1000:.2f} s',error=event.error_summary)
        db=self._db
        def finalize(context):
            repo=JobRepository(db)
            if not repo.get_job(snapshot['id']):
                metadata=self._metadata
                model_ok=not metadata or ModelRepository(db).upsert_model(metadata)
                repo.insert_job(kind='validation',job_id=snapshot['id'],status='PENDING',model_id=snapshot['model_id'] if model_ok else None,
                                input_source=snapshot['detail'],details=state['payload'])
            saved=repo.update_job_state(snapshot['id'],status=status,duration_ms=event.duration_ms,
                                       error_summary=event.error_summary,details=state['payload'])
            state['persisted']=bool(saved and (state['persisted'] if state['result'] is not None else True))
            if not state['persisted']:
                logger.error('Validation history persistence failed: %s',snapshot['id'])
            return None
        def done(final_event):
            if final_event.status.value!='SUCCESS':
                state['persisted']=False
            self.job=snapshot
            self.job_changed.emit(snapshot)
            self.finished.emit((snapshot,self.result,state))
            self.workflow.history_changed.emit()
        self.workflow._submit_read('validation_finalize',finalize,done)
