"""Artifact, dataset and traceability contracts independent of Qt."""
import dataclasses
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from damage_gui.model.metadata import sidecar_path
from damage_gui.model.registry import ModelLoadError, load_model, save_model
from damage_gui.services.dataset_service import inspect_dataset
from damage_gui.services.model_registry_service import ModelRegistryService
from damage_gui.services.training_service import TrainingService
from damage_gui.storage.repositories import JobRepository, ModelRepository
from synthetic_data import make_service, write_synthetic_dataset


@pytest.fixture
def dataset(tmp_path):
    directory=tmp_path/'data';directory.mkdir()
    write_synthetic_dataset(directory)
    return directory

@pytest.fixture
def bundle(dataset):return make_service(dataset).train_bundle('F')


def test_inspection_real_grid_gaps_shapes_and_invalid(dataset):
    info=inspect_dataset(dataset)
    assert info['samples']==12 and info['levels']['F']['shapes']=={'64 × 64':12}
    assert info['levels']['F']['grid_gaps']==0
    path=next(dataset.iterdir());path.unlink()
    assert inspect_dataset(dataset)['levels']['F']['grid_gaps']==1
    path.write_text('header\nbad\n')
    assert inspect_dataset(dataset)['levels']['F']['errors']


def test_duplicate_conditions_and_missing_levels(dataset):
    path=next(dataset.iterdir())
    duplicate=path.with_name(path.name.replace('_h_','_h_0'))
    duplicate.write_bytes(path.read_bytes())
    info=inspect_dataset(dataset)
    assert info['levels']['F']['duplicates']==1 and 'M' not in info['levels']


def test_atomic_save_preserves_existing_and_cleans_failed_serialization(tmp_path,bundle):
    path=tmp_path/'artifact.joblib'
    save_model(bundle,path,overwrite=False)
    before=path.read_bytes(),sidecar_path(path).read_bytes()
    with pytest.raises(FileExistsError):save_model(bundle,path,overwrite=False)
    assert before==(path.read_bytes(),sidecar_path(path).read_bytes())
    with patch('damage_gui.model.registry.joblib.dump',side_effect=RuntimeError('interrupted serialization')):
        with pytest.raises(RuntimeError):save_model(bundle,path)
    assert before==(path.read_bytes(),sidecar_path(path).read_bytes())
    assert not list(tmp_path.glob('.*'))
    assert load_model(path).metadata.model_id==bundle.metadata.model_id


def test_registration_activation_missing_and_trace(tmp_path,bundle):
    db=tmp_path/'trace.sqlite';service=ModelRegistryService(db)
    repo=JobRepository(db)
    assert ModelRepository(db).upsert_model(bundle.metadata)
    job_id=repo.insert_job(kind='training',model_id=bundle.metadata.model_id,details={'registration':'unregistered'})
    old_finished=repo.get_job(job_id)['finished_at']
    service.register(bundle)
    assert json.loads(repo.get_job(job_id)['details_json'])['registration']=='registered'
    assert repo.get_job(job_id)['finished_at']==old_finished
    with pytest.raises(ValueError):service.register(bundle)
    row=service.list_models()[0]
    active,path=service.activate(row)
    assert active.metadata.model_id==bundle.metadata.model_id
    assert service.list_models()[0]['status']=='ACTIVE'
    assert service.detail(row)['training_jobs'][0]['id']==job_id
    assert ModelRepository(db).list_models(training_data_hash=bundle.metadata.training_data_hash)[0]['id']==bundle.metadata.model_id
    Path(path).unlink()
    row=service.list_models()[0];assert row['status']=='MISSING'
    assert service.detail(row)['training_data_hash']==bundle.metadata.training_data_hash
    with pytest.raises(ModelLoadError):service.activate(row)


def test_legacy_and_draft_no_registry(tmp_path,dataset,bundle):
    service=ModelRegistryService(tmp_path/'trace.sqlite')
    result=TrainingService(make_service(dataset),report_dir=tmp_path,db_path=tmp_path/'trace.sqlite',record_db=False).train('F')
    assert not result.db_recorded and not service.list_models()
    legacy=dataclasses.replace(bundle,metadata=None)
    path=tmp_path/'legacy.joblib';save_model(legacy,path)
    assert load_model(path).metadata is None
    with pytest.raises(ValueError):service.register(legacy)


def test_history_filter_applies_before_pagination(tmp_path,bundle):
    db=tmp_path/'trace.sqlite';models=ModelRepository(db);models.upsert_model(bundle.metadata)
    repo=JobRepository(db)
    target=repo.insert_job(kind='training',model_id=bundle.metadata.model_id)
    repo.insert_job(kind='training')
    assert [row['id'] for row in repo.list_jobs(model_id=bundle.metadata.model_id,limit=1)]==[target]
