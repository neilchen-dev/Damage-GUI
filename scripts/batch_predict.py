"""批量预测 CLI 入口（向后兼容薄封装）。

实现已移至 damage_gui.cli 的 batch 子命令；本脚本保留原调用方式：
    python scripts/batch_predict.py --model m.joblib --input in.csv --output out.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["batch"] + sys.argv[1:]))
