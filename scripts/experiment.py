"""实验追踪 CLI（M3.5）：experiment list / show / compare（SQLite 存储）。

用法：
    python scripts/experiment.py list [--limit N]
    python scripts/experiment.py show <id>
    python scripts/experiment.py compare <id> <id> [id ...]
    （--db 可指定数据库文件，默认 examples/results/experiments/experiments.sqlite3）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui.experiments.tracking import (  # noqa: E402
    DEFAULT_DB,
    ExperimentStore,
    compare_runs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / DEFAULT_DB,
                        help="SQLite 实验库路径")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="列出实验记录（新记录在前）")
    list_parser.add_argument("--limit", type=int, default=50)

    show_parser = sub.add_parser("show", help="查看单条实验的完整记录")
    show_parser.add_argument("run_id", type=int)

    compare_parser = sub.add_parser("compare", help="并排对比若干实验记录")
    compare_parser.add_argument("run_ids", type=int, nargs="+")

    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"实验库不存在: {args.db}（先运行 scripts/run_experiments.py）")

    with ExperimentStore(args.db) as store:
        if args.command == "list":
            frame = store.list_runs(limit=args.limit)
            print(frame.to_string(index=False) if len(frame) else "（无实验记录）")
        elif args.command == "show":
            try:
                payload = store.get_run(args.run_id)
            except KeyError as exc:
                parser.error(str(exc))
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            try:
                frame = compare_runs(store, args.run_ids)
            except KeyError as exc:
                parser.error(str(exc))
            print(frame.to_string())


if __name__ == "__main__":
    main()
