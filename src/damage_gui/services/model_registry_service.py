"""Bridge the existing lifecycle registry with traceability repositories."""
import json
import time
from pathlib import Path

from damage_gui.model.lifecycle import ModelRegistry
from damage_gui.model.registry import load_model, save_model
from damage_gui.storage.repositories import JobRepository, ModelRepository


class ModelRegistryService:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        # Existing lifecycle schema is intentionally separate from trace models.
        self.lifecycle_path = self.db_path.with_name(self.db_path.stem + '_registry.sqlite')
        self.artifact_dir = self.db_path.parent / 'registered_models'

    def register(self, bundle):
        metadata = getattr(bundle, 'metadata', None)
        if metadata is None:
            raise ValueError('Legacy model: metadata incomplete; prediction remains available')
        with ModelRegistry(self.lifecycle_path) as registry:
            if metadata.model_id in set(registry.list_models()['model_id']):
                raise ValueError('Model ID already registered')
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            path = self.artifact_dir / f'model_{bundle.level.lower()}_{metadata.model_id}.joblib'
            save_started = time.perf_counter()
            if path.exists():
                # Recover an earlier interrupted registration without overwriting.
                existing = load_model(path)
                if not existing.metadata or existing.metadata.to_dict() != metadata.to_dict():
                    raise FileExistsError('Conflicting existing model artifact')
            else:
                save_model(bundle, path, overwrite=False)
            save_seconds = time.perf_counter() - save_started
            if not ModelRepository(self.db_path).upsert_model(metadata, str(path.resolve())):
                raise RuntimeError('Model file saved, but traceability registration failed')
            row_id = registry.register(path.resolve())
            repo = JobRepository(self.db_path)
            for job in repo.list_jobs(model_id=metadata.model_id, kind='training',
                                      limit=1000) or []:
                payload = json.loads(job.get('details_json') or '{}')
                payload.update(registration='registered', artifact_path=str(path.resolve()))
                updated = repo.update_job_state(job['id'], status=job['status'],
                                                finished_at=job.get('finished_at'), details=payload)
                if not updated:
                    raise RuntimeError('Registered model, but training trace update failed')
        return dict(row_id=row_id, model_id=metadata.model_id,
                    path=str(path.resolve()), save_seconds=save_seconds)

    def list_models(self):
        with ModelRegistry(self.lifecycle_path) as registry:
            rows = registry.list_models().to_dict('records')
        metadata = ModelRepository(self.db_path).list_models()
        if metadata is None:
            raise RuntimeError('Model metadata database unavailable')
        by_id = {row['id']:row for row in metadata}
        for row in rows:
            row['row_id'] = row['id']
            row.update(by_id.get(row['model_id'], {}))
            row['id'] = row['model_id']
            row['path'] = row['model_path']
            row['lifecycle_status'] = row['status']
            if not Path(row['path']).is_file():
                row['status'] = 'MISSING'
            elif row['status'] in ('DRAFT', 'VALIDATED'):
                row['status'] = 'AVAILABLE'
        return rows

    def detail(self, row):
        info = dict(row)
        path = Path(row['path'])
        info.update(exists=path.is_file(), size=path.stat().st_size if path.is_file() else None)
        repo = JobRepository(self.db_path)
        training = repo.list_jobs(limit=1000, kind='training', model_id=row['model_id'])
        validation = repo.list_jobs(limit=1, kind='validation', status='SUCCESS',
                                    model_id=row['model_id'])
        if training is None or validation is None:
            raise RuntimeError('Related history unavailable')
        info['training_jobs'] = training
        info['latest_validation'] = validation[0] if validation else None
        return info

    def activate(self, row):
        # Deserialize before changing persistent lifecycle state.
        bundle = load_model(row['path'])
        if bundle.metadata is None or bundle.metadata.model_id != row['model_id']:
            raise ValueError('Model identity does not match registry')
        with ModelRegistry(self.lifecycle_path) as registry:
            record = registry.get(row['row_id'])
            if record['status']=='DRAFT':
                # VALIDATED means evidence exists, never a quality threshold.
                if not bundle.metadata.validation.get('method'):
                    raise ValueError('Lifecycle requires recorded validation evidence')
                registry.transition(row['row_id'], 'VALIDATED')
                record = registry.get(row['row_id'])
            if record['status'] != 'ACTIVE':
                registry.transition(row['row_id'], 'ACTIVE')
        return bundle, row['path']
