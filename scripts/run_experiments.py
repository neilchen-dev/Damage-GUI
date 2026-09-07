"""M3.1 消融实验运行器：执行预设实验矩阵并落盘 CSV/JSON/MD 报告。

预设套件：
    design      四模型象限 {RBF, POD-RBF} × {质心对齐 关/开}
    baseline    M3.2 基线：最近邻 + 逐像素线性插值
                （线性基线指标须连同 Extrap% 凸包外回填比例解读）
    validation  验证策略对比（random / leave_h_out / leave_v_out /
                leave_deg_out / corner）
    pod         POD 模态数 K 扫描（附累计解释方差）
    rbf         RBF 核 × 平滑 × epsilon 参数网格

用法：
    python scripts/run_experiments.py --data-dir dist\\data --level F --suite design pod
    python scripts/run_experiments.py --synthetic          # CI 冒烟：合成数据
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from damage_gui.data.loader import DamageDataManager
from damage_gui.experiments.runner import (
    baseline_specs,
    design_quadrant_specs,
    pod_sweep_specs,
    rbf_param_specs,
    run_suite,
    save_report,
    validation_specs,
)
from damage_gui.experiments.tracking import DEFAULT_DB, ExperimentStore
from damage_gui.model.bundle import DamageModelService

SUITE_NAMES = ("design", "baseline", "validation", "pod", "rbf")

_SUMMARY_COLUMNS = (
    "experiment", "status", "mean_relative_error", "p95_hybrid_error",
    "r2", "dice", "centroid_error_m", "extrapolation_fraction",
    "train_time_seconds", "error",
)


def build_specs(name: str, pod_ks: tuple[int, ...]):
    if name == "design":
        return design_quadrant_specs()
    if name == "baseline":
        return baseline_specs()
    if name == "validation":
        return validation_specs()
    if name == "pod":
        return pod_sweep_specs(ks=pod_ks)
    if name == "rbf":
        return rbf_param_specs()
    raise ValueError(f"未知套件: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="真实数据目录（与 --synthetic 二选一）")
    parser.add_argument("--synthetic", action="store_true",
                        help="使用合成数据集（CI 冒烟，无需真实数据）")
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--suite", nargs="+", choices=SUITE_NAMES,
                        default=list(SUITE_NAMES))
    parser.add_argument("--pod-ks", type=int, nargs="+",
                        default=[5, 10, 15, 20, 25, 30])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "examples" / "results" / "experiments")
    parser.add_argument("--db", type=Path, default=ROOT / DEFAULT_DB,
                        help="SQLite 实验库路径（M3.5 追踪）")
    args = parser.parse_args()

    tmp = None
    if args.synthetic:
        sys.path.insert(0, str(ROOT / "tests"))
        from synthetic_data import make_synthetic_dataset

        tmp, data_dir = make_synthetic_dataset()
    elif args.data_dir is not None:
        data_dir = args.data_dir
    else:
        parser.error("需要 --data-dir 或 --synthetic")

    try:
        service = DamageModelService(DamageDataManager(data_dir))
        for suite_name in args.suite:
            specs = build_specs(suite_name, tuple(args.pod_ks))
            print(f"\n===== 套件 {suite_name}（{len(specs)} 个实验，"
                  f"等级 {args.level}）=====")
            results = run_suite(service, args.level, specs, suite=suite_name)
            paths = save_report(
                results, args.out, f"ablation_{args.level}_{suite_name}",
                level=args.level, data_dir=data_dir,
            )
            frame = pd.DataFrame([r.to_dict() for r in results])
            columns = [c for c in _SUMMARY_COLUMNS if c in frame.columns]
            print(frame[columns].to_string(index=False))
            print(f"报告已保存: {paths['csv'].parent} / "
                  f"{paths['csv'].name[:-4]}.*(csv|json|md)")
            with ExperimentStore(args.db) as store:
                ids = store.record(results, suite=suite_name)
            print(f"实验库已记录: {args.db.name} (id={ids})")
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    main()
