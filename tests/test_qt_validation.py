import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from damage_gui.config import Config
from damage_gui.qt.task_adapter import TaskAdapter
from damage_gui.qt.validation_workflow import ValidationWorkflow
from damage_gui.qt.workflow import Workflow
from damage_gui.services.validation_service import ValidationResult, ValidationService
from damage_gui.storage.repositories import JobRepository


def test_validation_workflow(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/archive/capture_qt_validation.py'),str(tmp_path)],
                          env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr

def test_adapter_delivers_fast_followup_finished():
    code='''
import time
from PySide6.QtWidgets import QApplication
from damage_gui.qt.task_adapter import TaskAdapter
app=QApplication([])
adapter=TaskAdapter()
finished=[]
def event(item):
    if item.type!='finished': return
    finished.append(item.kind)
    if item.kind=='lead':
        adapter.submit('tail',lambda context:42)
        while adapter.is_busy('tail'): time.sleep(.001)
adapter.event_received.connect(event)
adapter.submit('lead',lambda context:None)
while adapter.is_busy(): time.sleep(.001)
adapter._poll()
assert adapter._timer.isActive()
deadline=time.monotonic()+2
while 'tail' not in finished:
    app.processEvents()
    time.sleep(.001)
    assert time.monotonic()<deadline
adapter.stop()
'''
    result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},
                          capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr


def test_validation_sidecar_failure_is_reported_as_unpersisted(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    db=tmp_path/'trace.sqlite'
    (tmp_path/'validation_results').write_text('blocks directory creation')
    adapter=TaskAdapter()
    workflow=Workflow(adapter,db_path=db)
    controller=ValidationWorkflow(workflow)
    workflow.validation=controller
    class Bundle:
        level='F'
        model_type='rbf'
        metadata=None
        model=type('Model',(),{'n_components':None})()
        def resolved_config(self):return Config()
    monkeypatch.setattr(ValidationService,'run',lambda *args,**kwargs: ValidationResult([],[],[],[]))
    completed=[]
    controller.finished.connect(completed.append)
    controller.run(Bundle(),str(tmp_path),'random',{})
    deadline=time.monotonic()+5
    while not completed and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(.01)
    adapter.stop()
    assert completed
    job,_,state=completed[0]
    assert job['status']=='SUCCESS'
    assert state['persisted'] is False
    assert 'result_sidecar' not in state['payload']
    assert JobRepository(db).get_job(job['id'])['status']=='SUCCESS'
