"""Desktop UX acceptance using existing scientific workflows, without new services."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from PySide6.QtWidgets import QApplication, QFileDialog

from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.theme import build_stylesheet
from damage_gui.qt.widgets.workspace import CopyableValue, DetailView, WorkspaceHeader
from synthetic_data import make_service, write_synthetic_dataset


def main(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['DAMAGE_GUI_DB']=str(output/f'ux_{uuid.uuid4().hex[:8]}.sqlite')
    dataset=output/'synthetic_dataset';dataset.mkdir(exist_ok=True)
    write_synthetic_dataset(dataset,velocities=(100.,200.,300.),angles=(10.,20.,30.))
    app=QApplication([]);app.setStyleSheet(build_stylesheet());w=DamageQtMainWindow();w.show();w.translator.set_language('en')
    def wait(predicate,timeout=60):
        until=time.monotonic()+timeout
        while not predicate():
            app.processEvents();time.sleep(.005);assert time.monotonic()<until,'UX acceptance timed out'
        app.processEvents()
    def shot(name):app.processEvents();w.grab().save(str(output/f'{name}.png'))
    w._navigate('models');wait(lambda:w.registry_workspace.empty.isVisible());shot('registry_empty_en_1440x900')
    assert w.registry_workspace.empty.isVisible() and not w._act_current_run.isEnabled()
    w.registry_workspace.empty.button.click();assert w._current_key()=='training'
    training=w.training_workspace;training.base_config=make_service(dataset).config
    training.directory.setText(str(dataset));training.inspect();wait(lambda:training.run_button.isEnabled())
    training.model_type.setCurrentIndex(1);training.components.setValue(5)
    w._run_current();wait(lambda:not w.workflow.training.running);assert training.result
    assert isinstance(training.summary,DetailView) and len(training.summary.sections)==5
    hidden=training.summary.findChildren(__import__('PySide6.QtWidgets',fromlist=['QPlainTextEdit']).QPlainTextEdit)
    assert hidden and not hidden[0].isVisible()
    training.register_button.click();wait(lambda:training.registered and not w.registry_workspace._operation)
    w._navigate('models');registry=w.registry_workspace;wait(lambda:registry.info is not None)
    registry.activate_button.click();wait(lambda:w._prediction_panel.bundle is not None and not registry._operation)
    model_id=w._prediction_panel.bundle.metadata.model_id
    validation=w.validation_workspace;w._navigate('validation');validation.mode.setCurrentIndex(validation.mode.findData('leave_h_out'))
    wait(lambda:validation.run_button.isEnabled());validation.layer.setCurrentIndex(validation.layer.findData(3.));wait(lambda:validation.run_button.isEnabled())
    w._run_current();wait(lambda:not w.workflow.validation.running);assert validation.result
    panel=w._prediction_panel;w._navigate('prediction');panel.h_spin.setValue(2);panel.v_spin.setValue(200);panel.deg_spin.setValue(20)
    w._run_current();wait(lambda:not panel.is_running);assert panel.current_result
    batch=w.batch_workspace;source=output/'batch.csv';source.write_text('job_id,h,v,deg,level\n001,2,200,20,F\n002,3,100,10,F\n')
    w._navigate('batch');batch.load_csv(str(source));batch.validate();wait(lambda:batch.run_button.isEnabled())
    w._run_current();wait(lambda:not w.workflow.running);assert w.workflow.job['status']=='SUCCESS'
    w._model_history(dict(model_id=model_id));history=w.history_workspace;wait(lambda:len(history.model.rows)>=4)
    training_id=w.workflow.training.job['id'];history.selected_id=training_id;w.workflow.load_detail(training_id)
    wait(lambda:history._detail_data and history._detail_data[0]['id']==training_id)
    assert len(history.detail.sections)==5
    # Copy displays compact identifiers but retains exact values.
    full=CopyableValue(model_id,compact=True);full.resize(100,30);full.copy();assert QApplication.clipboard().text()==model_id
    registry.model.replace(registry.rows);registry.table.setCurrentIndex(registry.model.index(0,0));registry.table.copy_cell()
    assert QApplication.clipboard().text()==model_id
    batch.preview.setCurrentIndex(batch.preview_model.index(0,0));batch.preview.copy_row();assert '\t' in QApplication.clipboard().text()
    batch.search.setText('001');assert batch.preview_model.rowCount()==1;batch.search.clear()
    # Verify action scoping and reversible layout tools.
    w._navigate('models');assert not w._act_current_run.isEnabled()
    w._act_inspector.trigger();assert not w.inspector.isVisible();w._act_layout.trigger();assert w.inspector.isVisible()
    w._act_logs.trigger();assert not w._activity.is_collapsed and w._activity._tabs['logs'].isChecked()
    w._act_logs.trigger();assert w._activity.is_collapsed
    pages=('prediction','batch','validation','training','models','history')
    for language in ('en','zh'):
        w.translator.set_language(language)
        for width,height in ((1440,900),(1280,720),(1100,700)):
            w.resize(width,height);app.processEvents()
            for key in pages:
                w._navigate(key);wait(lambda:not w.task_adapter.is_busy() and not w.workflow._requests)
                header=w.prediction_header if key=='prediction' else w._pages[key].header
                assert isinstance(header,WorkspaceHeader)
                assert w.inspector.width()==280
                assert w.pages.width()>=700 or width==1100
                shot(f'{key}_{language}_{width}x{height}')
    w.resize(1440,900);w.translator.set_language('en');w._navigate('validation');validation.tabs.setCurrentIndex(1)
    validation.sort_buttons[0].click();shot('validation_sample_sort_en')
    validation.open_sample(validation.sample_model.index(0,0));shot('validation_comparison_en')
    # Export invokes the same existing JSON exporter; no modal success dialog.
    path=output/'validation_summary.json';selector=QFileDialog.getSaveFileName;QFileDialog.getSaveFileName=lambda *a,**kw:(str(path),'JSON')
    validation.export();QFileDialog.getSaveFileName=selector;assert path.is_file();shot('export_success_en')
    evidence=dict(database=str(w.workflow.db_path),model_id=model_id,screenshots=len(list(output.glob('*.png'))),
                  sizes=['1440x900','1280x720','1100x700'],languages=['en','zh'],workflows=list(pages))
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2))
    wait(lambda:not w.task_adapter.is_busy() and not w.workflow._requests);w.close();app.processEvents();print(json.dumps(evidence))

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else ROOT/'outputs/qt_phase24_ui')
