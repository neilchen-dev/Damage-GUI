"""Real five-mode validation acceptance with shared synthetic fields."""
import json
import os
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from PySide6.QtWidgets import QApplication, QFileDialog

from damage_gui.model.bundle import DamageModelService
from damage_gui.model.registry import save_model
from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet
from damage_gui.storage.repositories import JobRepository
from synthetic_data import make_service, write_synthetic_dataset


def main(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['DAMAGE_GUI_DB']=str(output/'validation.sqlite')
    with tempfile.TemporaryDirectory() as tmp:
        directory=Path(tmp)
        write_synthetic_dataset(directory,velocities=(100.,200.,300.),angles=(10.,20.,30.))
        bundle=make_service(directory).train_bundle('F')
        app=QApplication([]);app.setStyleSheet(build_stylesheet())
        w=DamageQtMainWindow();w.translator.set_language('en');w.show()
        def wait(predicate,timeout=60):
            deadline=time.monotonic()+timeout
            while not predicate():
                app.processEvents();time.sleep(.004)
                assert time.monotonic()<deadline,'Validation timed out'
            app.processEvents()
        def shot(name):
            app.processEvents();w.grab().save(str(output/f'{name}.png'))
        model_path=directory/'model.joblib';save_model(bundle,str(model_path))
        selector=QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName=lambda *args,**kwargs:(str(model_path),'')
        w._act_open.trigger();QFileDialog.getOpenFileName=selector
        w._navigate('validation');page=w.validation_workspace
        wait(lambda:page.run_button.isEnabled())
        shot('validation_ready_en')
        evidence={}
        def run(mode,layer=None):
            page.mode.setCurrentIndex(page.mode.findData(mode))
            if layer is not None:
                page.layer.setCurrentIndex(page.layer.findData(layer))
            wait(lambda:page.run_button.isEnabled())
            started=time.monotonic();page.run()
            wait(lambda:w.workflow.validation.job['status']=='RUNNING')
            shot('validation_running_en')
            wait(lambda:not w.workflow.validation.running)
            assert w.workflow.validation.job['status']=='SUCCESS',w.workflow.validation.job
            result=w.workflow.validation.result
            assert result.samples and result.accuracy
            job_id=w.workflow.validation.job['id']
            row=JobRepository(w.workflow.db_path).get_job(job_id)
            payload=json.loads(row['details_json'])
            assert row['kind']=='validation' and row['model_id']==bundle.metadata.model_id
            assert payload['validation_mode']==mode and payload['sample_count']==len(result.samples)
            assert Path(payload['result_sidecar']).exists()
            evidence[mode]=dict(elapsed_seconds=round(time.monotonic()-started,4),samples=len(result.samples),folds=len(result.folds))
            return job_id,result
        random_id,random=run('random')
        shot('random_complete_en')
        height_id,height=run('leave_h_out',3.)
        assert {row['h'] for row in height.samples}=={3.}
        shot('height_complete_en')
        raw=page.summary.toPlainText();page.metric_view.setCurrentIndex(1)
        assert 'Smoothed' in page.summary.toPlainText() and raw!=page.summary.toPlainText()
        assert w.workflow.validation.job['id']==height_id
        shot('smoothed_metrics_en')
        page.metric_view.setCurrentIndex(0);shot('raw_metrics_en')
        page.tabs.setCurrentIndex(3);shot('error_distribution_en')
        page.tabs.setCurrentIndex(1);shot('sample_table_en')
        page.sample_model.sort(5,__import__('PySide6.QtCore',fromlist=['Qt']).Qt.DescendingOrder)
        shot('worst_case_en')
        page.open_sample(page.sample_model.index(0,0))
        assert len(page.comparison.figure.axes)>=3
        axes=[axis for axis in page.comparison.figure.axes if axis.images]
        assert axes[0].images[0].get_clim()==axes[1].images[0].get_clim()
        error=axes[2].images[0].get_clim();assert abs(error[0]+error[1])<1e-10
        shot('sample_comparison_en')
        w.translator.set_language('zh');shot('sample_comparison_zh');w.translator.set_language('en')
        page.tabs.setCurrentIndex(0)
        run('leave_v_out');run('leave_deg_out')
        page.corner_v.setValue(300);page.corner_deg.setValue(30)
        corner_id,corner=run('corner')
        assert all(row['v']>=300 and row['deg']>=30 for row in corner.samples)
        shot('corner_complete_en')
        w._navigate('history');history=w.history_workspace
        wait(lambda:any(row['kind']=='validation' for row in history.model.rows))
        history.selected_id=height_id;w.workflow.load_detail(height_id)
        wait(lambda:history._detail_data and history._detail_data[0]['id']==height_id)
        assert 'training_data_hash' in history.detail.toPlainText()
        assert 'Per-sample fields unavailable' in history.detail.toPlainText()
        shot('validation_history_en')
        w.translator.set_language('zh');shot('validation_history_zh');w.translator.set_language('en')
        history.restore_button.click();assert page.mode.currentData()=='leave_h_out' and page.layer.currentData()==3.
        assert not w.workflow.validation.running
        # Solver failure after a successful compatibility check: FAILED persists.
        wait(lambda:page.run_button.isEnabled())
        original=DamageModelService.train_bundle
        def failed(*args,**kwargs): raise RuntimeError('Validation fixture failure')
        DamageModelService.train_bundle=failed
        page.run();wait(lambda:not w.workflow.validation.running)
        assert w.workflow.validation.job['status']=='FAILED'
        assert JobRepository(w.workflow.db_path).get_job(w.workflow.validation.job['id'])['error_summary']=='Validation fixture failure'
        DamageModelService.train_bundle=original
        # Cooperative cancellation uses the real algorithm after a brief fixture delay.
        def slow(*args,**kwargs):
            time.sleep(.15);return original(*args,**kwargs)
        DamageModelService.train_bundle=slow
        wait(lambda:page.run_button.isEnabled());page.run()
        wait(lambda:w.workflow.validation.job['status']=='RUNNING')
        w.workflow.validation.cancel();wait(lambda:not w.workflow.validation.running)
        assert w.workflow.validation.job['status']=='CANCELLED'
        assert JobRepository(w.workflow.db_path).get_job(w.workflow.validation.job['id'])['status']=='CANCELLED'
        DamageModelService.train_bundle=original
        # POD-RBF runs through the same validation adapter.
        pod=make_service(directory).train_bundle('F',model_type='pod_rbf',pod_n_components=5)
        page.set_bundle(pod);page.mode.setCurrentIndex(0);wait(lambda:page.run_button.isEnabled());page.run()
        wait(lambda:not w.workflow.validation.running);assert w.workflow.validation.job['status']=='SUCCESS'
        # Ground-truth absence disables Run before execution.
        page.data_edit.clear();wait(lambda:not w.task_adapter.is_busy());assert not page.run_button.isEnabled()
        with closing(sqlite3.connect(w.workflow.db_path)) as connection:
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert connection.execute('PRAGMA user_version').fetchone()[0]==7
            assert connection.execute("SELECT COUNT(*) FROM prediction_results r JOIN jobs j ON j.id=r.job_id WHERE j.kind='validation'").fetchone()[0]==0
        wait(lambda:not w.task_adapter.is_busy());w.close();wait(lambda:not w.isVisible())
        evidence['screenshots']=len(list(output.glob('*.png')))
        (output/'evidence.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(evidence))
if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else ROOT/'outputs'/'qt_phase22')
