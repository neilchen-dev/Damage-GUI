"""Real Qt + PredictionService + SQLite end-to-end acceptance."""
import os
import subprocess
import sys
from pathlib import Path


def test_prediction_traceability(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/capture_qt_prediction_traceability.py'),str(tmp_path)],
                          env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
    assert (tmp_path/'traceability.sqlite').exists()
