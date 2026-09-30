"""Phase 2.1 real Qt acceptance, direct SQLite checks and bounded history benchmarks."""
import dataclasses
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

from damage_gui.model.registry import save_model
from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet
from damage_gui.storage.db import init_database
from damage_gui.storage.repositories import (
    JobRepository,
    ModelRepository,
)
from synthetic_data import make_service, write_synthetic_dataset


def main(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary)
        write_synthetic_dataset(directory)
        trained=dataclasses.replace(make_service(directory).train_bundle('F'),data_dir='')
        db=output/'traceability.sqlite'
        os.environ['DAMAGE_GUI_DB']=str(db)
        model_path=directory/'synthetic.joblib'
        save_model(trained,str(model_path))
        app=QApplication([])
        app.setStyleSheet(build_stylesheet())
        window=DamageQtMainWindow()
        window.translator.set_language('en')
        window.show()
        def wait(predicate,timeout=30):
            deadline=time.monotonic()+timeout
            while not predicate():
                app.processEvents()
                time.sleep(.003)
                assert time.monotonic()<deadline,'Qt workflow timed out'
            app.processEvents()
        def shot(name):
            app.processEvents()
            window.grab().save(str(output/f'{name}.png'))
        selector=QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName=lambda *args,**kwargs:(str(model_path),'')
        window._act_open.trigger()
        QFileDialog.getOpenFileName=selector
        panel=window._prediction_panel
        assert panel.bundle.metadata.model_id==trained.metadata.model_id
        def predict(h,v,deg):
            window._navigate('prediction')
            panel.h_spin.setValue(h)
            panel.v_spin.setValue(v)
            panel.deg_spin.setValue(deg)
            panel._on_predict()
            assert panel.is_running
            wait(lambda:not panel.is_running)
            return window.workflow.prediction_job['id'],panel.current_result
        def detail(job_id):
            window._navigate('history')
            history=window.history_workspace
            wait(lambda:history.model.rowCount()>0)
            history.selected_id=job_id
            window.workflow.load_detail(job_id)
            wait(lambda:history._detail_data is not None and history._detail_data[0]['id']==job_id)
            return history
        high_id,high=predict(3,100,10)
        assert high.ood_report.level=='high'
        assert window.workflow.prediction_job['status']=='SUCCESS'
        window._activity.expand()
        shot('prediction_success_activity_en')
        history=detail(high_id)
        try:
            wait(lambda:'training_data_hash' in history.detail.toPlainText(),timeout=10)
        except AssertionError:
            # CI-only flake diagnostics: dump persisted rows + rendered text.
            with closing(sqlite3.connect(db)) as connection:
                print('DIAG jobs:',[dict(row) for row in connection.execute('SELECT id,kind,status,model_id FROM jobs')])
                print('DIAG models:',[dict(row) for row in connection.execute('SELECT id,artifact_path FROM models')])
            print('DIAG detail:',history.detail.toPlainText())
            raise
        shot('prediction_high_history_en')
        low_id,low=predict(2,150,20)
        assert low.ood_report.level=='low'
        history=detail(low_id)
        shot('prediction_low_history_en')
        shot('prediction_detail_en')
        panel.h_spin.setValue(1)
        history.restore_button.click()
        assert (panel.h_spin.value(),panel.v_spin.value(),panel.deg_spin.value(),panel.level_combo.currentText())==(2,150,20,'F')
        assert not panel.is_running
        shot('restore_inputs_en')
        # Every repeated prediction is a distinct persisted job.
        before=JobRepository(db).count_jobs()
        identifiers=set()
        latencies=[]
        for _ in range(20):
            started=time.monotonic()
            job_id,result=predict(3,100,10)
            latencies.append(time.monotonic()-started)
            identifiers.add(job_id)
        assert len(identifiers)==20
        assert JobRepository(db).count_jobs()==before+20
        # Direct DB verification: foreign keys and exact service-produced scalar values.
        with closing(sqlite3.connect(db)) as connection, connection:
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
            for job_id,result in ((high_id,high),(low_id,low)):
                row=connection.execute('SELECT j.status,j.model_id,r.h,r.v,r.deg,r.level,r.peak_intensity,r.damage_area_ratio,r.ood_level,r.ood_distance FROM jobs j JOIN prediction_results r ON r.job_id=j.id WHERE j.id=?',(job_id,)).fetchone()
                assert row[:6]==('SUCCESS',trained.metadata.model_id,result.condition.h,result.condition.v,result.condition.deg,'F')
                assert row[6:]==(result.peak_intensity,result.damage_area_ratio,result.ood_report.level,result.ood_report.distance)
        service=panel.prediction_service
        class Failure:
            def predict(self,*args,**kwargs):
                raise RuntimeError('Invalid model state')
        panel.prediction_service=Failure()
        failure_id,_=predict(2,150,20)
        failure=JobRepository(db).get_job(failure_id)
        assert failure['status']=='FAILED' and failure['error_summary']=='Invalid model state'
        panel.prediction_service=service
        class Slow:
            def predict(self,*args,**kwargs):
                time.sleep(.08)
                return service.predict(*args,**kwargs)
        panel.prediction_service=Slow()
        panel._on_predict()
        wait(lambda:window.workflow.prediction_job['status']=='RUNNING')
        assert window.task_adapter.cancel('prediction')
        wait(lambda:not panel.is_running)
        cancel_id=window.workflow.prediction_job['id']
        assert JobRepository(db).get_job(cancel_id)['status']=='CANCELLED'
        panel.prediction_service=service
        # Old nullable rows use the unchanged schema and remain readable.
        old_id=JobRepository(db).insert_job(kind='prediction', status='SUCCESS')
        old_history=detail(old_id)
        assert 'Metadata unavailable' in old_history.detail.toPlainText()
        assert not old_history.restore_button.isEnabled()
        # Existing Batch remains part of the same history.
        csv=directory/'batch.csv'
        csv.write_text('h,v,deg\n3,100,10\n2,150,20\n')
        window._navigate('batch')
        batch=window.batch_workspace
        batch.load_csv(csv)
        batch.validate()
        wait(lambda:batch.parsed is not None)
        batch.run()
        wait(lambda:window.workflow.report is not None)
        wait(lambda:not window.task_adapter.is_busy())
        assert window.workflow.report.success_count==2
        assert ModelRepository(db).get_model(trained.metadata.model_id)['artifact_path']==str(model_path)
        window._navigate('history')
        history.refresh()
        wait(lambda:any(row['kind']=='batch_prediction' for row in history.model.rows))
        shot('mixed_history_en')
        history.kind.setCurrentIndex(1)
        wait(lambda:history.model.rows and all(row['kind']=='prediction' for row in history.model.rows))
        history.status.setCurrentIndex(4)
        wait(lambda:history.model.rows and all(row['status']=='FAILED' for row in history.model.rows))
        history.status.setCurrentIndex(0)
        history.kind.setCurrentIndex(0)
        # Old metadata-free bundles and missing files must remain readable.
        original=panel.bundle
        panel._bind_bundle(dataclasses.replace(original,metadata=None),str(model_path))
        legacy_id,_=predict(3,100,10)
        history=detail(legacy_id)
        assert 'Metadata unavailable' in history.detail.toPlainText()
        panel._bind_bundle(original,str(model_path))
        model_path.unlink()
        history=detail(high_id)
        assert 'Model file unavailable' in history.detail.toPlainText()
        window.translator.set_language('zh')
        shot('prediction_detail_zh')
        # Explicit DB degradation preserves field and result.
        window.workflow.db_path=directory
        degraded_id,result=predict(2,150,20)
        assert result.ood_report.level=='low'
        assert not window.workflow._prediction_state['persisted']
        assert '追溯记录写入失败' in window._activity.status.text()
        shot('persistence_failed_zh')
        window.workflow.db_path=db
        window.translator.set_language('en')
        assert 'history persistence failed' in window._activity.status.text()
        shot('persistence_failed_en')
        # Session panel bounds; complete history remains in repositories.
        for i in range(110):
            window._activity.update_job(dict(id=f'cap_{i}',type='Prediction',status='SUCCESS'))
        assert window._activity.jobs_model.rowCount()==100
        benchmarks={}
        bench_db=directory/'history.sqlite'
        assert init_database(bench_db)
        for count in (1000,10000):
            # Test fixture bulk insertion, never an application/UI SQL path.
            with closing(sqlite3.connect(bench_db)) as connection, connection:
                connection.execute('DELETE FROM jobs')
                connection.executemany("INSERT INTO jobs(id,kind,status,created_at,details_json) VALUES (?,'prediction','SUCCESS','2026-09-29T00:00:00Z','{}')",[(f'{i:05d}',) for i in range(count)])
                connection.execute("INSERT INTO jobs(id,kind,status,created_at) VALUES ('batch','batch_prediction','SUCCESS','2026-09-29T00:00:00Z')")
            window.workflow.db_path=bench_db
            history.kind.setCurrentIndex(0)
            history.status.setCurrentIndex(0)
            history.offset=0
            started=time.monotonic()
            history.refresh()
            wait(lambda:history.message.text()!='…')
            benchmarks[str(count)]=round(time.monotonic()-started,4)
            first=[row['id'] for row in history.model.rows]
            assert len(first)==1000 and first[0]=='batch'
            history._page(1000)
            wait(lambda:history.message.text()!='…')
            second=[row['id'] for row in history.model.rows]
            assert not set(first)&set(second)
            assert first==[row['id'] for row in JobRepository(bench_db).list_jobs(limit=1000)]
        window.close()
        wait(lambda:not window.isVisible())
        evidence=dict(history_first_page_seconds=benchmarks,repeated_predictions=20,
                      mean_ui_completion_seconds=round(sum(latencies)/len(latencies),4),
                      foreign_keys='verified',screenshots=len(list(output.glob('*.png'))),database=str(db))
        (output/'evidence.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence))

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else ROOT/'outputs'/'qt_phase21')
