"""Qt workflow presentation helpers. All service and repository I/O runs in TaskManager."""
from __future__ import annotations

import csv
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QObject, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView

from damage_gui.data.loader import DamageDataManager
from damage_gui.services.batch_service import BatchService
from damage_gui.storage.db import resolve_db_path
from damage_gui.storage.repositories import (
    JobRepository,
    ModelRepository,
    PredictionResultRepository,
)

logger = logging.getLogger('damage_gui.qt.workflow')


class RecordsModel(QAbstractTableModel):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.columns = tuple(columns)
        self.headers = {}
        self.display_values = {}
        self.rows = []
        self._all_rows = []
        self.filter_text = ""

    def rowCount(self, parent=None):
        return len(self.rows) if parent is None or not parent.isValid() else 0

    def columnCount(self, parent=None):
        return len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        value = row.get(self.columns[index.column()], '')
        if role == Qt.ToolTipRole:
            return '—' if value is None else str(value)
        if role == Qt.DisplayRole:
            column=self.columns[index.column()]
            display=self.display_values.get(column,{}).get(value,value) if isinstance(value,(str,int,float,bool)) else value
            if display is None:return '—'
            text=str(display)
            if column in ('model_id','id','job_id','training_data_hash') and len(text)>20:
                return text[:10]+'…'
            if column in ('input_source','output','output_path','artifact_path') and ('/' in text or '\\' in text):
                return Path(text).name
            return text
        if role == Qt.ForegroundRole and self.columns[index.column()]=='status':
            from damage_gui.qt.theme import QtTheme
            from damage_gui.qt.widgets.status_badge import status_role
            theme=QtTheme()
            colors={'success':theme.success,'running':theme.primary,'error':theme.danger,'warning':theme.busy,'neutral':theme.muted}
            return QColor(colors[status_role(str(value))])
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.headers.get(self.columns[section],self.columns[section]) if orientation == Qt.Horizontal else str(section + 1)

    def replace(self, rows):
        self.beginResetModel()
        self._all_rows = list(rows)
        self.rows = [row for row in self._all_rows if not self.filter_text or self.filter_text in " ".join(str(value) for value in row.values()).lower()]
        self.endResetModel()

    def filter(self, text):
        self.filter_text=text.strip().lower()
        self.replace(self._all_rows)

    def sort(self, column, order=Qt.AscendingOrder):
        # Persistent selection follows records across sorting.
        old = self.persistentIndexList()
        identities = [id(self.rows[index.row()]) for index in old]
        self.layoutAboutToBeChanged.emit()
        def key(row):
            value = row.get(self.columns[column])
            return (value is None, 0 if isinstance(value, (int, float)) else 1,
                    value if isinstance(value, (int, float)) else str(value or ''))
        self.rows.sort(key=key, reverse=order == Qt.DescendingOrder)
        locations = {id(row): i for i, row in enumerate(self.rows)}
        self.changePersistentIndexList(old, [self.index(locations[identity], index.column())
                                           for identity, index in zip(identities, old, strict=False)])
        self.layoutChanged.emit()


def table(columns, *, dark=False):
    from damage_gui.qt.widgets.workflow_table import WorkflowTable
    view = WorkflowTable()
    view.setObjectName('workflowTableDark' if dark else 'workflowTable')
    model = RecordsModel(columns, view)
    view.setModel(model)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.setSortingEnabled(True)
    view.setShowGrid(False)
    view.verticalHeader().setDefaultSectionSize(30)
    view.verticalHeader().hide()
    view.horizontalHeader().setFixedHeight(30)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    view.horizontalHeader().setDefaultSectionSize(130)
    view.horizontalHeader().setStretchLastSection(True)
    return view, model


def details(job):
    try:
        return json.loads(job.get('details_json') or '{}')
    except (ValueError, TypeError):
        return {}


class Workflow(QObject):
    prediction_finished = Signal(object)
    prediction_job_changed = Signal(object)
    validated = Signal(object)
    validation_failed = Signal(str)
    job_changed = Signal(object)
    completed = Signal(object)
    history_changed = Signal()
    history_loaded = Signal(object)
    detail_loaded = Signal(object)

    def __init__(self, adapter, db_path=None, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.db_path = resolve_db_path(db_path)
        self.prediction_job = None
        self.job = None
        self.report = None
        self._validation_token = 0
        self._history_token = 0
        self._requests = {}
        adapter.event_received.connect(self._event)

    def _submit_read(self, prefix, work, callback):
        kind = f'{prefix}_{uuid.uuid4().hex}'
        self._requests[kind] = callback
        self.adapter.submit(kind, work)

    def validate(self, path, level):
        self._validation_token += 1
        token = self._validation_token
        def work(context):
            parsed = BatchService().parse_csv(path, default_level=level)
            errors = {row.line_no: row.error for row in parsed.invalid}
            preview = []
            with Path(path).open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                for i, raw in enumerate(reader, 2):
                    if len(preview) >= 100:
                        break
                    row = {key.strip().lower(): value for key, value in raw.items() if key}
                    row['job_id'] = row.get('job_id') or f'{i-1:04d}'
                    row['level'] = row.get('level') or level
                    row['status'] = 'invalid' if i in errors else 'valid'
                    row['error'] = errors.get(i, '')
                    preview.append(row)
            return (parsed, preview, str(Path(path).resolve()))
        def finish(event):
            if token != self._validation_token:
                return
            if event.status.value == 'SUCCESS':
                self.validated.emit(event.result)
            else:
                self.validation_failed.emit(event.error_summary or 'Unable to read CSV')
        self._submit_read('batch_validation', work, finish)

    def invalidate_validation(self):
        self._validation_token += 1

    @property
    def scientific_busy(self):
        validation=getattr(self,'validation',None)
        training=getattr(self,'training',None)
        return getattr(self,'model_operation',False) or self.running or self.prediction_running or (validation is not None and validation.running) or (training is not None and training.running)

    @property
    def running(self):
        return self.job is not None and self.job['status'] in ('PENDING', 'RUNNING')

    def run(self, bundle, parsed, input_path, output_path='', truth_path=''):
        if self.scientific_busy:
            raise RuntimeError('Another prediction is running')
        job_id = uuid.uuid4().hex
        metadata = getattr(bundle, 'metadata', None)
        model_id = metadata.model_id if metadata else None
        requested = Path(output_path).expanduser() if output_path else Path(input_path).parent / datetime.now().strftime('batch_result_%Y%m%d_%H%M%S.csv')
        self.report = None
        self._batch_metadata = metadata
        self._started = time.monotonic()
        self.job = dict(id=job_id, type='Batch', status='PENDING', progress=f'0 / {parsed.total}',
                        elapsed='—', detail=f'{parsed.total} rows', model_id=model_id, input=input_path, output='', total=parsed.total)
        self.job_changed.emit(dict(self.job))
        job_details = dict(total=parsed.total, input_file=input_path, output_file='',
                           model_id=model_id, truth_directory=truth_path or None)
        def work(context):
            started = time.monotonic()
            repo = JobRepository(self.db_path)
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.exception('Traceability directory unavailable; calculation will continue')
            model_ok = not metadata or ModelRepository(self.db_path).upsert_model(metadata)
            recorded = repo.insert_job(kind='batch_prediction', job_id=job_id, status='PENDING',
                                       model_id=model_id if model_ok else None,
                                       input_source=input_path, details=job_details)
            repo.update_job_state(job_id, status='RUNNING', started_at=datetime.now(timezone.utc).isoformat())
            owned_path = None
            try:
                requested.parent.mkdir(parents=True, exist_ok=True)
                candidate = requested
                suffix = 0
                while True:
                    try:
                        with candidate.open('x'):
                            pass
                        owned_path = candidate
                        break
                    except FileExistsError:
                        suffix += 1
                        candidate = requested.with_name(f'{requested.stem}_{suffix}{requested.suffix}')
                job_details['output_file'] = str(candidate.resolve())
                service = BatchService(config=bundle.resolved_config())
                manager = DamageDataManager(truth_path) if truth_path else None
                report = service.run(bundle, parsed, data_manager=manager, output_path=candidate,
                                     db_path=self.db_path, input_source=input_path, job_id=job_id,
                                     progress=context.report_progress, cancel_check=context.cancel_check)
                context.report_progress(len(report.rows), report.total, '')
                job_details.update(success=report.success_count, failed=report.failed_count,
                                   completed=len(report.rows), cancelled=report.cancelled)
                state = 'CANCELLED' if report.cancelled or context.cancel_check() else 'SUCCESS'
                saved = repo.update_job_state(job_id, status=state, duration_ms=report.duration_ms,
                                             details=job_details)
                report.db_recorded = bool(report.db_recorded and recorded and saved and model_ok)
                return report
            except Exception as exc:
                repo.update_job_state(job_id, status='FAILED', error_summary=str(exc)[:500],
                                      duration_ms=int((time.monotonic()-started)*1000), details=job_details)
                if owned_path and owned_path.exists() and owned_path.stat().st_size == 0:
                    owned_path.unlink()
                raise
        self.adapter.submit('qt_batch', work)

    @property
    def prediction_running(self):
        return self.prediction_job is not None and self.prediction_job['status'] in ('PENDING', 'RUNNING')

    def run_prediction(self, service, bundle, condition, artifact_path=''):
        if self.scientific_busy:
            raise RuntimeError('Another prediction is running')
        job_id = uuid.uuid4().hex
        metadata = getattr(bundle, 'metadata', None)
        model_id = metadata.model_id if metadata else None
        db_path = self.db_path
        payload = dict(level=bundle.level, h=condition.h, v=condition.v, deg=condition.deg)
        input_text = f'{bundle.level} / h={condition.h:g} / v={condition.v:g} / θ={condition.deg:g}'
        self.prediction_job = dict(id=job_id, type='Prediction', status='PENDING', detail=input_text,
                                   progress='—', elapsed='—', model_id=model_id)
        self.prediction_job_changed.emit(dict(self.prediction_job))
        state = dict(result=None, persisted=False, details=payload, metadata=metadata, db_path=db_path, artifact_path=artifact_path)
        self._prediction_state = state
        def work(context):
            repo = JobRepository(db_path)
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.exception('Traceability directory unavailable')
            model_ok = not metadata or ModelRepository(db_path).upsert_model(metadata, artifact_path or None)
            recorded = repo.insert_job(kind='prediction', job_id=job_id, status='PENDING',
                                      model_id=model_id if model_ok else None,
                                      input_source=input_text, details=payload)
            running_saved = repo.update_job_state(job_id, status='RUNNING', started_at=datetime.now(timezone.utc).isoformat())
            try:
                if context.cancel_check():
                    return state
                result = service.predict(bundle, condition, config=bundle.resolved_config())
                state['result'] = result
                ood = result.ood_report
                metrics = result.core_metrics or {}
                row = dict(job_id=job_id, **payload, status='SUCCESS',
                           ood_level=ood.level if ood else None, ood_distance=ood.distance if ood else None,
                           peak_intensity=result.peak_intensity, damage_area_ratio=result.damage_area_ratio,
                           duration_ms=result.elapsed_ms, mean_relative_error=metrics.get('MeanRelativeError'),
                           p95_hybrid_error=metrics.get('P95HybridError'))
                payload.update(confidence=ood.level.upper() if ood else None, prediction_elapsed_ms=result.elapsed_ms)
                state['row'] = row
                result_saved = PredictionResultRepository(db_path).record_batch_results(job_id=job_id, rows=[row])
                state['persisted'] = bool(model_ok and recorded and running_saved and result_saved)
                return state
            except Exception as exc:
                state['error'] = str(exc)[:500]
                raise
        self.adapter.submit('prediction', work)
        return job_id

    def _prediction_event(self, event):
        job = self.prediction_job
        if job is None:
            return
        # Keep the presentation RUNNING until terminal persistence finishes.
        if event.type != 'finished':
            job['status'] = event.status.value
            self.prediction_job_changed.emit(dict(job))
            return
        state = self._prediction_state
        snapshot = dict(job, status=event.status.value,
                        elapsed=f'{event.duration_ms or 0} ms', error=event.error_summary)
        def finalize(context):
            repo = JobRepository(state['db_path'])
            existing = repo.get_job(snapshot['id'])
            if existing is None:
                metadata = state['metadata']
                model_ok = not metadata or ModelRepository(state['db_path']).upsert_model(metadata, state['artifact_path'] or None)
                created = repo.insert_job(kind='prediction', job_id=snapshot['id'], status='PENDING',
                                         model_id=snapshot['model_id'] if model_ok else None,
                                         input_source=snapshot['detail'], details=state['details'])
            else:
                created = True
            saved = repo.update_job_state(snapshot['id'], status=snapshot['status'],
                                          duration_ms=event.duration_ms, error_summary=event.error_summary,
                                          details=state['details'])
            state['persisted'] = bool(created and saved and (state['persisted'] if state['result'] else True))
            if not state['persisted']:
                logger.error('Prediction history persistence failed: job=%s', snapshot['id'])
            return None
        def finished(final_event):
            if final_event.status.value != 'SUCCESS':
                state['persisted'] = False
            self.prediction_job = snapshot
            self.prediction_job_changed.emit(snapshot)
            self.prediction_finished.emit((snapshot, state))
            self.history_changed.emit()
        self._submit_read('prediction_finalize', finalize, finished)

    def cancel(self):
        return self.adapter.cancel('qt_batch')

    def load_history(self, kind='', status='', offset=0, model_id=''):
        self._history_token += 1
        token = self._history_token
        def work(context):
            repo = JobRepository(self.db_path)
            rows = repo.list_jobs(limit=1000, offset=offset, kind=kind, status=status, model_id=model_id)
            if rows is None:
                raise RuntimeError('History database unavailable')
            return [row for row in rows if (not kind or row['kind'] == kind)
                    and (not status or row['status'] == status)]
        self._submit_read('history', work, lambda event: self.history_loaded.emit(event) if token == self._history_token else None)

    def load_detail(self, job_id):
        def work(context):
            job = JobRepository(self.db_path).get_job(job_id)
            if job is None:
                raise RuntimeError('Job unavailable')
            model = ModelRepository(self.db_path).get_model(job['model_id']) if job['model_id'] else None
            if job['kind']=='validation':
                from pathlib import Path
                payload=details(job)
                try:
                    sidecar=payload.get('result_sidecar')
                    content=json.loads(Path(sidecar).read_text(encoding='utf-8')) if sidecar else {}
                    rows=content.get('samples',[])[:1000]
                except (OSError,ValueError):
                    rows=[]
            else:
                rows = PredictionResultRepository(self.db_path).list_results(job_id)
            return job, model, rows
        self._submit_read('detail', work, lambda event: self.detail_loaded.emit(event))

    def _event(self, event):
        if event.kind == 'prediction':
            self._prediction_event(event)
        if event.kind in self._requests and event.type == 'finished':
            self._requests.pop(event.kind)(event)
        if event.kind != 'qt_batch' or self.job is None:
            return
        self.job.update(status=event.status.value, progress=f'{event.done} / {event.total or self.job["total"]}',
                        elapsed=f'{event.duration_ms/1000 if event.duration_ms is not None else time.monotonic()-self._started:.2f} s')
        self.job_changed.emit(dict(self.job))
        if event.type == 'finished':
            self.report = event.result
            self.job['error'] = event.error_summary
            if self.report:
                self.job['output'] = str(self.report.output_path or '')
            snapshot = dict(self.job)
            # TaskManager owns the final state, including a late cooperative cancel.
            report_snapshot = self.report
            metadata_snapshot = self._batch_metadata
            def reconcile(context):
                repo = JobRepository(self.db_path)
                job = repo.get_job(snapshot['id'])
                if job:
                    saved = repo.update_job_state(snapshot['id'], status=snapshot['status'],
                                                 duration_ms=event.duration_ms, error_summary=event.error_summary)
                    if report_snapshot and not saved:
                        report_snapshot.db_recorded = False
                elif snapshot['status'] == 'CANCELLED':
                    model_ok = not metadata_snapshot or ModelRepository(self.db_path).upsert_model(metadata_snapshot)
                    repo.insert_job(kind='batch_prediction', job_id=snapshot['id'], status='CANCELLED',
                                    model_id=snapshot['model_id'] if model_ok else None,
                                    input_source=snapshot['input'], duration_ms=event.duration_ms,
                                    details={'total':snapshot['total'], 'completed':0, 'cancelled':True})
                return None
            self._submit_read('batch_finalize' , reconcile, lambda event: self.history_changed.emit())
            self.job_changed.emit(snapshot)
            self.completed.emit((snapshot, self.report))
