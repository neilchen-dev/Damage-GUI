"""再生成数值回归黄金值：tests/data/regression_golden.json。

在模型算法、预处理或有意的数据集变更后运行一次并提交结果；
禁止为了让测试变绿而随手再生成——先解释偏差来源。

用法：
    python scripts/regen_regression_golden.py [--output tests/data/regression_golden.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from regression_tools import GOLDEN_PATH, build_snapshot_in_tempdir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="再生成数值回归黄金值")
    parser.add_argument(
        "--output", default=str(GOLDEN_PATH), help="输出 JSON 路径"
    )
    args = parser.parse_args(argv)

    snapshot, tmp = build_snapshot_in_tempdir()
    try:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"黄金值已写入: {output}")
        return 0
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
