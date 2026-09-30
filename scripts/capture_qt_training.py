"""Real training → registration → activation → prediction/validation trace E2E."""
import dataclasses
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from PySide6.QtWidgets import QApplication

from damage_gui.model.registry import load_model, save_model
from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet
from damage_gui.services.model_registry_service import ModelRegistryService
from damage_gui.services.training_service import TrainingService
from damage_gui.storage.repositories import JobRepository, ModelRepository
from synthetic_data import make_service, write_synthetic_dataset


def main(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['DAMAGE_GUI_DB']=str(output/f'training_{uuid.uuid4().hex[:8]}.sqlite')
    directory=output/'synthetic_dataset';directory.mkdir(exist_ok=True)
    write_synthetic_dataset(directory,velocities=(100.,200.,300.),angles=(10.,20.,30.))
    app=QApplication([]);app.setStyleSheet(build_stylesheet())
    w=DamageQtMainWindow();w.translator.set_language('en');w.show()
    def wait(predicate,timeout=60):
        deadline=time.monotonic()+timeout
        while not predicate():
            app.processEvents();time.sleep(.004)
            assert time.monotonic()<deadline,'Training acceptance timed out'
        app.processEvents()
    def shot(name):
        app.processEvents();w.grab().save(str(output/f'{name}.png'))
    w._navigate('training');page=w.training_workspace
    page.base_config=make_service(directory).config
    assert not page.run_button.isEnabled();shot('training_ready_en')
    page.directory.setText(str(directory));page.inspect()
    wait(lambda:page.dataset is not None)
    assert page.dataset['samples']==27 and page.dataset['levels']['F']['valid']==27
    assert page.run_button.isEnabled();shot('dataset_loaded_en')
    page.level.setCurrentText('M');assert not page.run_button.isEnabled();page.level.setCurrentText('F')
    page.model_type.setCurrentIndex(1);page.components.setValue(5)
    page.inspector.advanced.setChecked(True);shot('training_parameters_en');page.inspector.advanced.setChecked(False)
    started=time.perf_counter();page.run()
    wait(lambda:w.workflow.training.job['status']=='RUNNING');shot('training_running_en')
    assert not w._act_open.isEnabled() and not w.registry_workspace.activate_button.isEnabled()
    wait(lambda:not w.workflow.training.running)
    assert w.workflow.training.job['status']=='SUCCESS',w.workflow.training.job
    training_id=w.workflow.training.job['id'];bundle=page.result.bundle;model_id=bundle.metadata.model_id
    assert page.register_button.isEnabled() and 'Unregistered' in page.summary.toPlainText()
    service=ModelRegistryService(w.workflow.db_path)
    assert not service.list_models()
    assert ModelRepository(w.workflow.db_path).get_model(model_id)['artifact_path'] is None
    shot('training_complete_en');shot('model_unregistered_en')
    page.tabs.setCurrentIndex(2);shot('pod_spectrum_en');page.tabs.setCurrentIndex(1)
    evidence=dict(database=str(w.workflow.db_path),dataset_load=page.dataset['elapsed_seconds'],training_duration=bundle.train_time_seconds,training_workflow_elapsed=time.perf_counter()-started,
                  training_samples=len(bundle.train_conditions),model_id=model_id,training_job_id=training_id)
    page.register_button.click()
    wait(lambda:page.registered and not w.registry_workspace._operation)
    assert len(service.list_models())==1
    path=Path(service.list_models()[0]['path']);assert path.is_file()
    assert load_model(path).metadata.model_id==model_id
    try:service.register(bundle)
    except ValueError:pass
    else:raise AssertionError('Duplicate registration accepted')
    w._navigate('models');registry=w.registry_workspace
    wait(lambda:bool(registry.rows) and registry.info is not None)
    shot('registry_list_en');shot('registry_detail_en')
    registry.activate_button.click()
    wait(lambda:w._prediction_panel.bundle is not None and not registry._operation)
    assert w._prediction_panel.bundle.metadata.model_id==model_id
    assert w.batch_workspace.bundle.metadata.model_id==model_id
    assert w.validation_workspace.bundle.metadata.model_id==model_id
    w._navigate('models');wait(lambda:registry.info is not None and registry.info['status']=='ACTIVE');shot('active_model_en')
    w._navigate('prediction');panel=w._prediction_panel
    panel.h_spin.setValue(2);panel.v_spin.setValue(200);panel.deg_spin.setValue(20)
    w._act_run.trigger();wait(lambda:not panel.is_running)
    assert panel.current_result is not None
    prediction_id=w.workflow.prediction_job['id'];shot('registered_prediction_en')
    validation=w.validation_workspace;w._navigate('validation')
    validation.mode.setCurrentIndex(validation.mode.findData('leave_h_out'))
    wait(lambda:validation.run_button.isEnabled())
    validation.layer.setCurrentIndex(validation.layer.findData(3.))
    wait(lambda:validation.run_button.isEnabled());validation.run()
    wait(lambda:not w.workflow.validation.running)
    assert w.workflow.validation.job['status']=='SUCCESS'
    validation_id=w.workflow.validation.job['id'];shot('registered_validation_en')
    w._model_history(dict(model_id=model_id));history=w.history_workspace
    wait(lambda:len(history.model.rows)>=3)
    assert {row['kind'] for row in history.model.rows}>= {'training','prediction','validation'}
    history.kind.setCurrentIndex(history.kind.findData('training'))
    wait(lambda:history.model.rows and all(row['kind']=='training' for row in history.model.rows))
    history.selected_id=training_id;w.workflow.load_detail(training_id)
    wait(lambda:history._detail_data and history._detail_data[0]['id']==training_id)
    assert bundle.metadata.training_data_hash in history.detail.toPlainText()
    shot('training_history_en');shot('traceability_detail_en')
    w._navigate('models');wait(lambda:registry.info is not None and registry.info.get('latest_validation'))
    assert registry.info['latest_validation']['id']==validation_id;shot('registry_validation_link_en')
    registry.validation_button.click()
    wait(lambda:history._detail_data and history._detail_data[0]['id']==validation_id)
    shot('validation_history_link_en')
    w.translator.set_language('zh');w._navigate('training');shot('training_complete_zh')
    w._navigate('models');wait(lambda:registry.info is not None);shot('registry_detail_zh');w.translator.set_language('en')
    # Missing artifacts retain model/job metadata, never enable activation.
    path.rename(path.with_suffix('.temporarily_missing'))
    registry.refresh();wait(lambda:registry.info is not None and registry.info['status']=='MISSING')
    assert not registry.activate_button.isEnabled();shot('missing_model_en')
    path.with_suffix('.temporarily_missing').rename(path)
    # Legacy identity is not fabricated, registration denied, prediction remains available.
    legacy=dataclasses.replace(bundle,metadata=None);legacy_path=output/'legacy.joblib';save_model(legacy,legacy_path)
    panel._bind_bundle(load_model(legacy_path),str(legacy_path));w._navigate('models')
    registry.status.setCurrentIndex(registry.status.findData('LEGACY'))
    wait(lambda:registry.info is not None and registry.info['status']=='LEGACY')
    assert not registry.register_button.isEnabled();shot('legacy_model_en')
    w._navigate('prediction');w._act_run.trigger();wait(lambda:not panel.is_running);assert panel.current_result
    try:service.register(legacy)
    except ValueError:pass
    else:raise AssertionError('Legacy registration fabricated metadata')
    # Actual RBF training, fatal service failure, cooperative cancellation.
    w._navigate('training');page.model_type.setCurrentIndex(0);page.run()
    wait(lambda:not w.workflow.training.running);assert w.workflow.training.job['status']=='SUCCESS'
    original=TrainingService.train
    def fail(self,*args,**kwargs):raise RuntimeError('Synthetic training failure')
    TrainingService.train=fail;page.run();wait(lambda:not w.workflow.training.running)
    failed_id=w.workflow.training.job['id'];assert w.workflow.training.job['status']=='FAILED' and page.result is None
    assert JobRepository(w.workflow.db_path).get_job(failed_id)['status']=='FAILED'
    shot('training_failed_en')
    def slow(self,*args,**kwargs):
        kwargs['progress'](0,1,'Cooperative cancellation boundary')
        time.sleep(.15)
        return original(self,*args,**kwargs)
    TrainingService.train=slow;page.run();wait(lambda:w.workflow.training.job['status']=='RUNNING');page.cancel_button.click()
    wait(lambda:not w.workflow.training.running);TrainingService.train=original
    cancelled_id=w.workflow.training.job['id'];assert w.workflow.training.job['status']=='CANCELLED' and page.result is None
    assert JobRepository(w.workflow.db_path).get_job(cancelled_id)['status']=='CANCELLED';shot('training_cancelled_en')
    invalid=output/'invalid_dataset';invalid.mkdir(exist_ok=True)
    (invalid/'DamageMatrix_F_h_10_v_1000_deg_100').write_text('header\nbad\n')
    page.directory.setText(str(invalid));page.inspect();wait(lambda:page.dataset is not None)
    assert not page.run_button.isEnabled();shot('invalid_dataset_en')
    assert len(service.list_models())==1
    assert ModelRepository(w.workflow.db_path).list_models(training_data_hash=bundle.metadata.training_data_hash)
    for job_id in (training_id,prediction_id,validation_id):
        assert JobRepository(w.workflow.db_path).get_job(job_id)['model_id']==model_id
    evidence.update(registry.last_elapsed, prediction_job_id=prediction_id,validation_job_id=validation_id,
                    screenshots=len(list(output.glob('*.png'))))
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2))
    wait(lambda:not w.task_adapter.is_busy());w.close();app.processEvents()
    print(json.dumps(evidence))

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else ROOT/'outputs/qt_phase23')
