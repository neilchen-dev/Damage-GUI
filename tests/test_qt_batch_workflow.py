"""Real headless Qt workflow regression, using the shared synthetic fixtures."""
import os
import subprocess
import sys
from pathlib import Path


def test_batch_workflow(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable,str(root/'scripts/capture_qt_batch_workflow.py'),str(tmp_path)],
                            env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},
                            capture_output=True,text=True,timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path/'evidence.json').exists()
