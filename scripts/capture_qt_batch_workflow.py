"""Exercise Phase 2.0 with synthetic data, save screenshots and timing evidence."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from PySide6.QtWidgets import QApplication, QFileDialog

from damage_gui.model.registry import save_model
from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet
from damage_gui.storage.repositories import JobRepository, PredictionResultRepository
from synthetic_data import make_service, write_synthetic_dataset


def main(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    temp = tempfile.TemporaryDirectory()
    directory = Path(temp.name)
    os.environ['DAMAGE_GUI_DB'] = str(directory/'trace.db')
    write_synthetic_dataset(directory)
    bundle = make_service(directory).train_bundle('F')
    app = QApplication([])
    app.setStyleSheet(build_stylesheet())
    window = DamageQtMainWindow()
    window.translator.set_language('en')
    window.show()
    window.resize(1440,900)
    page = window.batch_workspace
    model_path = str(directory/'synthetic.joblib')
    save_model(bundle, model_path)
    original_selector = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = lambda *args, **kwargs: (model_path, 'CSV (*.csv)')
    window._act_open.trigger()
    QFileDialog.getOpenFileName = original_selector
    bundle = page.bundle
    assert bundle is window._prediction_panel.bundle
    window._navigate('batch')
    def wait(predicate,timeout=20):
        deadline = time.monotonic()+timeout
        while not predicate():
            app.processEvents()
            time.sleep(.005)
            assert time.monotonic()<deadline,'Timed out'
        app.processEvents()
    def shot(name):
        app.processEvents()
        window.grab().save(str(output/f'{name}.png'))
    def validate(path):
        page.load_csv(path)
        page.validate()
        wait(lambda: page.parsed is not None or page.validate_button.isEnabled())
    shot('batch_no_csv_en_1440x900')
    timings = {}
    for count in (100,1000,10000):
        source = directory/f'preview_{count}.csv'
        source.write_text('job_id,h,v,deg,level\n'+''.join(f'{i:05d},2,150,15,F\n' for i in range(count)))
        started = time.monotonic()
        validate(source)
        assert page.parsed.total == count
        assert page.preview_model.rowCount()==100
        timings[str(count)] = round(time.monotonic()-started,4)
    source = directory/'batch.csv'
    source.write_text('job_id,h,v,deg,level\n001,2,150,15,F\n002,3,100,10,F\n')
    validate(source)
    shot('batch_validated_en_1440x900')
    original = bundle.model.predict_matrix
    def slow(condition):
        time.sleep(.06)
        return original(condition)
    bundle.model.predict_matrix = slow
    page.run()
    wait(lambda: window.workflow.job['status']=='RUNNING')
    shot('batch_running_en_1440x900')
    # UI model switch must leave the submitted bundle untouched.
    window._prediction_panel._bind_bundle(make_service(directory).train_bundle('F'), model_path)
    window._navigate('batch')
    wait(lambda: window.workflow.report is not None)
    wait(lambda: not window.task_adapter.is_busy())
    report = window.workflow.report
    assert report.success_count==2 and report.db_recorded
    assert report.model_id==bundle.metadata.model_id
    first_job = window.workflow.job['id']
    assert JobRepository(window.workflow.db_path).get_job(first_job)['status']=='SUCCESS'
    assert len(PredictionResultRepository(window.workflow.db_path).list_results(first_job))==2
    assert Path(report.output_path).exists()
    shot('batch_completed_en_1440x900')
    window._activity.expand()
    shot('jobs_expanded_en_1440x900')
    window._activity._tabs['results'].click()
    shot('results_en_1440x900')
    # Existing output must survive and suffix the next run.
    protected = directory/'protected.csv'
    protected.write_text('keep me')
    page.output_edit.setText(str(protected))
    source.write_text('job_id,h,v,deg,level\n001,2,150,15,F\n002,2,150,15,M\n003,bad,150,15,F\n')
    validate(source)
    assert len(page.parsed.invalid)==1
    page.run()
    wait(lambda: window.workflow.report is not None)
    wait(lambda: not window.task_adapter.is_busy())
    assert window.workflow.report.failed_count==2
    assert window.workflow.job['status']=='SUCCESS'
    assert protected.read_text()=='keep me'
    shot('batch_row_errors_en_1440x900')
    window.translator.set_language('zh')
    window.resize(1280,720)
    shot('batch_row_errors_zh_1280x720')
    window._navigate('history')
    wait(lambda: window.history_workspace.model.rowCount()>=2)
    shot('history_list_zh_1280x720')
    history = window.history_workspace
    history.jobs.setCurrentIndex(history.model.index(0,0))
    wait(lambda: bool(history.detail.toPlainText()))
    assert 'training_data_hash' in history.detail.toPlainText()
    shot('history_detail_zh_1280x720')
    window.translator.set_language('en')
    window.resize(1440,900)
    shot('history_detail_en_1440x900')
    # Fatal output failure (parent is a file).
    window._navigate('batch')
    page.output_edit.setText(str(protected/'invalid.csv'))
    validate(source)
    page.run()
    wait(lambda: window.workflow.job['status']=='FAILED')
    wait(lambda: not window.task_adapter.is_busy())
    assert JobRepository(window.workflow.db_path).get_job(window.workflow.job['id'])['status']=='FAILED'
    # Cancellation keeps the completed row(s), CSV and matching terminal DB state.
    page.set_bundle(bundle)
    source.write_text('h,v,deg\n'+'2,150,15\n'*30)
    page.output_edit.clear()
    validate(source)
    page.run()
    wait(lambda: window.workflow.job['progress'].split('/')[0].strip() not in ('0',''))
    page.cancel()
    wait(lambda: window.workflow.job['status']=='CANCELLED')
    wait(lambda: not window.task_adapter.is_busy())
    report=window.workflow.report
    assert report and 0<len(report.rows)<30
    assert Path(report.output_path).exists()
    assert JobRepository(window.workflow.db_path).get_job(window.workflow.job['id'])['status']=='CANCELLED'
    shot('batch_cancelled_en_1440x900')
    # File-level validation failure.
    bad=directory/'bad.csv'
    bad.write_text('a,b\n1,2\n')
    validate(bad)
    assert page.parsed is None and not page.run_button.isEnabled()
    # closeEvent shows a MODAL confirm dialog while the adapter is busy (the
    # async validation above may still be in flight) and hangs offscreen.
    wait(lambda: not window.task_adapter.is_busy() and not window.workflow._requests)
    window.close()
    wait(lambda: not window.isVisible())
    # Reopening reloads persistent history without session Jobs.
    other=DamageQtMainWindow()
    other._navigate('history')
    wait(lambda: other.history_workspace.model.rowCount()>=4)
    assert other._activity.jobs_model.rowCount()==0
    other.close()
    wait(lambda: not other.task_adapter.is_busy())
    degraded = DamageQtMainWindow()
    degraded.workflow.db_path = directory  # Existing directory cannot be a SQLite file.
    degraded.batch_workspace.set_bundle(bundle)
    source.write_text('h,v,deg\n2,150,15\n')
    degraded.batch_workspace.load_csv(source)
    degraded.batch_workspace.validate()
    wait(lambda: degraded.batch_workspace.parsed is not None)
    degraded.batch_workspace.run()
    wait(lambda: degraded.workflow.report is not None)
    wait(lambda: not degraded.task_adapter.is_busy())
    assert degraded.workflow.job['status'] == 'SUCCESS'
    assert not degraded.workflow.report.db_recorded
    assert Path(degraded.workflow.report.output_path).exists()
    assert '未完整写入' in degraded.batch_workspace.summary.text()
    degraded.close()
    evidence=dict(preview_seconds=timings,preview_limit=100,workflow='success, row failures, fatal failure, cancellation, model lock, persistence',screenshots=len(list(output.glob('*.png'))))
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))
    temp.cleanup()

if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else ROOT/'outputs'/'qt_phase20')
