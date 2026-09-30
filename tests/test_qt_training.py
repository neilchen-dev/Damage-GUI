"""Real Qt training lifecycle, registry and related trace acceptance."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('PySide6')


def test_training_registry_e2e(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/capture_qt_training.py'),str(tmp_path)],
                          cwd=root,env=dict(os.environ,QT_QPA_PLATFORM='offscreen'),capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert len(list(tmp_path.glob('*.png')))>=14
