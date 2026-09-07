"""模型生命周期 CLI（M3.6）：register / promote / list（SQLite 登记库）。

状态机：DRAFT → VALIDATED → ACTIVE → ARCHIVED（任何状态可直接归档）。
家族 = 毁伤等级（F/M/P），同等级至多一个 ACTIVE，晋升时自动归档原 ACTIVE。

用法：
    python scripts/model_lifecycle.py register <模型.joblib> [--notes ...]
    python scripts/model_lifecycle.py promote <id> VALIDATED|ACTIVE|ARCHIVED
    python scripts/model_lifecycle.py list [--level F] [--status ACTIVE]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui.errors import LifecycleError  # noqa: E402
from damage_gui.model.lifecycle import (  # noqa: E402
    DEFAULT_LIFECYCLE_DB,
    MODEL_STATES,
    ModelRegistry,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / DEFAULT_LIFECYCLE_DB,
                        help="生命周期登记库路径")
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="登记已保存的模型（初始 DRAFT）")
    reg.add_argument("model_path", type=Path)
    reg.add_argument("--notes", default="", help="登记备注")

    promote = sub.add_parser("promote", help="按状态机转移模型状态")
    promote.add_argument("row_id", type=int)
    promote.add_argument("target", choices=MODEL_STATES)
    promote.add_argument("--notes", default=None, help="追加备注")

    list_parser = sub.add_parser("list", help="列出登记库中的模型")
    list_parser.add_argument("--level", choices=("F", "M", "P"), default=None)
    list_parser.add_argument("--status", choices=MODEL_STATES, default=None)

    args = parser.parse_args()
    try:
        with ModelRegistry(args.db) as registry:
            if args.command == "register":
                row_id = registry.register(args.model_path, notes=args.notes)
                record = registry.get(row_id)
                print(
                    f"已登记: id={row_id} model_id={record['model_id'][:8]}…"
                    f" 等级={record['level']} 类型={record['model_type']}"
                    f" 状态={record['status']}"
                )
            elif args.command == "promote":
                record = registry.transition(args.row_id, args.target, notes=args.notes)
                for old_id in record.get("replaced", []):
                    print(f"同等级原 ACTIVE 已自动归档: id={old_id}")
                print(f"id={args.row_id} 状态已更新为 {record['status']}")
            else:
                frame = registry.list_models(level=args.level, status=args.status)
                if frame.empty:
                    print("（登记库为空）")
                else:
                    frame["model_id"] = frame["model_id"].str[:8] + "…"
                    print(frame.to_string(index=False))
    except LifecycleError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
