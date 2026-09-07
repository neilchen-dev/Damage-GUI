"""M3.4 不确定度校准研究：LOO 残差 + kNN 估计 + 校准分箱 + 可靠性曲线。

用法：
    python scripts/uncertainty_study.py --data-dir dist\\data --level F
    python scripts/uncertainty_study.py --synthetic          # CI 冒烟
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui.data.loader import DamageDataManager
from damage_gui.experiments.uncertainty import (
    run_uncertainty_study,
    save_uncertainty_report,
)
from damage_gui.model.bundle import DamageModelService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="真实数据目录（与 --synthetic 二选一）")
    parser.add_argument("--synthetic", action="store_true",
                        help="使用合成数据集（CI 冒烟，无需真实数据）")
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--model-type", choices=("rbf", "pod_rbf"),
                        default="rbf")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--bins", type=int, default=4)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "examples" / "results" / "uncertainty")
    args = parser.parse_args()

    tmp = None
    if args.synthetic:
        sys.path.insert(0, str(ROOT / "tests"))
        from synthetic_data import make_service, make_synthetic_dataset

        tmp, _data_dir = make_synthetic_dataset()
        service = make_service(Path(tmp.name))
        data_dir = "synthetic"
    elif args.data_dir is not None:
        service = DamageModelService(DamageDataManager(args.data_dir))
        data_dir = args.data_dir
    else:
        parser.error("需要 --data-dir 或 --synthetic")

    try:
        study = run_uncertainty_study(
            service, args.level,
            model_type=args.model_type, k=args.k, n_bins=args.bins,
        )
        name = f"uncertainty_{args.level}_{args.model_type}"
        paths = save_uncertainty_report(study, args.out, name, data_dir=data_dir)
        summary = study["summary"]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\n报告已保存: {paths['csv'].parent} / {name}.*(csv|json|md|png)")
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    main()
