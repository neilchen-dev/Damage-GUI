"""M3.8 轻量 Drift 报告 CLI：训练工况分布 vs 查询工况分布（KS 检验）。

用法：
    python scripts/drift_report.py --data-dir dist\\data --level F --queries new_queries.csv
    python scripts/drift_report.py --data-dir dist\\data --level F          # 训练集自检
    python scripts/drift_report.py ... --out examples/results/drift        # 落盘 JSON/MD

查询 CSV 需含 h, v, deg 三列（与批量预测输入同口径）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from damage_gui.config import CONFIG  # noqa: E402
from damage_gui.data.loader import DamageDataManager  # noqa: E402
from damage_gui.errors import DataValidationError  # noqa: E402
from damage_gui.experiments.drift import (  # noqa: E402
    drift_report,
    load_query_conditions,
    save_drift_report,
    verdict_line,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="训练数据目录（如 dist/data）")
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--queries", type=Path, default=None,
                        help="查询工况 CSV（h,v,deg 列）；缺省用训练集自身自检")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="KS 检验显著性水平（默认 0.05）")
    parser.add_argument("--out", type=Path, default=None,
                        help="报告输出目录（缺省仅打印结论不落盘）")
    parser.add_argument("--name", type=str, default=None,
                        help="报告文件名（默认 drift_<等级>）")
    args = parser.parse_args()

    try:
        records = DamageDataManager(args.data_dir).get_level_records(args.level)
        if not records:
            raise DataValidationError(f"数据目录中没有等级 {args.level} 的训练工况")
        train = np.array(
            [record.condition.as_array() for record in records], dtype=np.float64
        )
        if args.queries is not None:
            queries = load_query_conditions(args.queries)
        else:
            queries = train  # 自检：训练分布对自身，KS 统计量必为 0
    except DataValidationError as exc:
        parser.error(str(exc))

    report = drift_report(train, queries, CONFIG, alpha=args.alpha)
    print(verdict_line(report))
    if args.queries is None:
        print("（自检模式：查询集 = 训练集，用于验证报告管线）")
    for name, item in report["dimensions"].items():
        flag = "漂移" if item["drift"] else "正常"
        print(
            f"  {name}: KS={item['ks_statistic']:.4f} p={item['p_value']:.4f} "
            f"[{flag}] 越界 {item['out_of_range']}/{report['n_queries']}"
        )

    if args.out is not None:
        paths = save_drift_report(
            report, args.out, args.name or f"drift_{args.level}", level=args.level
        )
        print(f"报告已保存: {paths['md']}")


if __name__ == "__main__":
    main()
