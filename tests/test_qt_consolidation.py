"""Structural desktop UX checks; screenshots are acceptance artifacts, not baselines."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('PySide6')


def test_desktop_consolidation_e2e(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/capture_qt_consolidation.py'),str(tmp_path)],cwd=root,
                          env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert len(list(tmp_path.glob('*.png')))>=36


def test_common_status_copy_and_shortcuts(tmp_path):
    code=r'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from damage_gui.qt.main_window import DamageQtMainWindow
from damage_gui.qt.widgets.workspace import DetailView,CopyableValue
from damage_gui.qt.widgets.status_badge import StatusIndicator,status_role
from damage_gui.qt.workflow import table
app=QApplication([]);w=DamageQtMainWindow();w.show();app.processEvents()
for state,role in [('SUCCESS','success'),('ACTIVE','success'),('RUNNING','running'),('FAILED','error'),('CANCELLED','warning'),('LEGACY','neutral')]:
    status=StatusIndicator();status.set_state(state);assert status.property('role')=='status-'+role
value=CopyableValue('sha256:'+'a'*64,compact=True);value.resize(110,30);value.show();app.processEvents()
assert len(value.text())<len(value.full_value);value.copy_action.trigger();assert QApplication.clipboard().text()==value.full_value
view,model=table(('id','status'));model.replace([{'id':'0123456789abcdef0123456789abcdef','status':'SUCCESS'}]);view.show();view.setCurrentIndex(model.index(0,0))
QTest.keyClick(view,Qt.Key_C,Qt.ControlModifier);assert '0123456789abcdef0123456789abcdef' in QApplication.clipboard().text()
assert model.data(model.index(0,0),Qt.ToolTipRole)=='0123456789abcdef0123456789abcdef'
w._navigate('history');assert not w._act_current_run.isEnabled()
w.activateWindow();app.processEvents();w._act_search.trigger();app.processEvents();assert w.history_workspace.model_filter.hasFocus()
w._act_inspector.trigger();assert not w.inspector.isVisible();w._act_layout.trigger();assert w.inspector.isVisible()
w._act_logs.trigger();assert not w._activity.is_collapsed;w._act_logs.trigger();assert w._activity.is_collapsed
w.close()
'''
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',DAMAGE_GUI_DB=str(tmp_path/'ui.sqlite')),capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
