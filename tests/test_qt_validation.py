import os
import subprocess
import sys
from pathlib import Path


def test_validation_workflow(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/capture_qt_validation.py'),str(tmp_path)],
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
                          capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
