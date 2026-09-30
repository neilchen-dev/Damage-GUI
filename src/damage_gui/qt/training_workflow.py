"""Training lifecycle; completed bundles stay drafts until explicit registration."""
import dataclasses
import time
import uuid
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal

from damage_gui.data.loader import DamageDataManager
from damage_gui.model.bundle import DamageModelService
from damage_gui.qt.validation_workflow import clean
from damage_gui.services.training_service import TrainingService
from damage_gui.storage.repositories import JobRepository, ModelRepository


class TrainingWorkflow(QObject):
    job_changed = Signal(object)
    finished = Signal(object)

    def __init__(self, workflow):
        super().__init__(workflow)
        self.workflow, self.job, self.result = workflow, None, None
        workflow.adapter.event_received.connect(self._event)

    @property
    def running(self):
        return self.job is not None and self.job['status'] in ('PENDING', 'RUNNING')

    def run(self, directory, level, config):
        if self.workflow.scientific_busy:
            return
        job_id = uuid.uuid4().hex
        self.result = None
        self._started = time.monotonic()
        self.job = dict(id=job_id, type='Training', status='PENDING',
                        detail=f'{level} · {config.model_type.upper().replace("_", "-")}',
                        model_id=None, progress='—', elapsed='—')
        payload = dict(dataset=str(directory), level=level, model_type=config.model_type,
                       config=dataclasses.asdict(config), validation_mode=config.validation_mode,
                       registration='unregistered')
        self.state = dict(payload=payload, result=None, persisted=False)
        state, db = self.state, self.workflow.db_path
        self.job_changed.emit(dict(self.job))
        def work(context):
            db.parent.mkdir(parents=True, exist_ok=True)
            repo = JobRepository(db)
            created = repo.insert_job(kind='training', job_id=job_id, status='PENDING',
                                      input_source=str(directory), details=payload)
            running = repo.update_job_state(job_id, status='RUNNING', started_at=datetime.now(timezone.utc).isoformat())
            report_dir = db.parent / 'training_reports' / job_id
            report_dir.mkdir(parents=True, exist_ok=True)
            result = TrainingService(DamageModelService(DamageDataManager(directory), config),
                                     db_path=db, report_dir=report_dir, record_db=False).train(
                level, progress=context.report_progress, cancel_check=context.cancel_check)
            state['result'] = result
            bundle = result.bundle
            payload.update(output_model_id=bundle.metadata.model_id, metadata=bundle.metadata.to_dict(),
                           accuracy=clean(bundle.accuracy_report.to_dict('records')),
                           training_samples=len(bundle.train_conditions), test_samples=len(bundle.test_conditions),
                           train_time_seconds=bundle.train_time_seconds,
                           accuracy_report_path=str(result.accuracy_report_path),
                           condition_report_path=str(result.condition_report_path))
            # Metadata-only trace row supports the FK, not a lifecycle registration.
            model_ok = ModelRepository(db).upsert_model(bundle.metadata)
            state['persisted'] = bool(created and running and model_ok)
            return result
        self.workflow.adapter.submit('training', work)

    def cancel(self):
        return self.workflow.adapter.cancel('training')

    def _event(self, event):
        if event.kind != 'training' or self.job is None:
            return
        if event.type != 'finished':
            self.job.update(status=event.status.value, stage=event.stage,
                            progress=f'{event.done} / {event.total}' if event.total else '—',
                            elapsed=f'{time.monotonic()-self._started:.1f} s')
            self.job_changed.emit(dict(self.job))
            return
        state, db = self.state, self.workflow.db_path
        # Late cancellation must not expose an apparently usable draft.
        self.result = state['result'] if event.status.value == 'SUCCESS' else None
        if self.result is None:
            state['payload'].pop('output_model_id', None)
            state['payload']['registration'] = 'no_usable_model'
        snapshot = dict(self.job, status=event.status.value, error=event.error_summary,
                        elapsed=f'{(event.duration_ms or 0)/1000:.2f} s',
                        model_id=self.result.bundle.metadata.model_id if self.result else None)
        def finalize(context):
            repo = JobRepository(db)
            if repo.get_job(snapshot['id']) is None:
                repo.insert_job(kind='training', job_id=snapshot['id'], status='PENDING',
                                input_source=state['payload']['dataset'], details=clean(state['payload']))
            saved = repo.update_job_state(snapshot['id'], status=snapshot['status'], model_id=snapshot['model_id'],
                                         duration_ms=event.duration_ms, error_summary=event.error_summary,
                                         details=clean(state['payload']))
            state['persisted'] = bool(saved and (state['persisted'] if self.result else True))
        def done(final_event):
            if final_event.status.value != 'SUCCESS':
                state['persisted'] = False
            self.job = snapshot
            self.job_changed.emit(snapshot)
            self.finished.emit((snapshot, self.result, state))
            self.workflow.history_changed.emit()
        self.workflow._submit_read('training_finalize', finalize, done)
