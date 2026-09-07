"""M3.3 性能基准：训练时间 / 峰值内存 / 产物大小 / 冷热推理延迟。

用法：
    python scripts/benchmark.py --data-dir dist\\data --level F
    python scripts/benchmark.py --synthetic --batch-sizes 10 50   # CI 冒烟
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from damage_gui.data.loader import DamageDataManager
from damage_gui.experiments.benchmark import (
    run_model_benchmark,
    save_benchmark_report,
)
from damage_gui.model.bundle import DamageModelService

MODEL_TYPES = ("rbf", "pod_rbf", "nn", "linear")

_SUMMARY_COLUMNS = (
    "model_type", "mode", "batch_size", "mean_ms", "p95_ms",
    "throughput_per_s", "train_time_seconds", "peak_memory_mb",
    "artifact_bytes",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="真实数据目录（与 --synthetic 二选一）")
    parser.add_argument("--synthetic", action="store_true",
                        help="使用合成数据集（CI 冒烟，无需真实数据）")
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--model-types", nargs="+", choices=MODEL_TYPES,
                        default=list(MODEL_TYPES))
    parser.add_argument("--batch-sizes", type=int, nargs="+",
                        default=[10, 100, 1000])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "examples" / "results" / "benchmark")
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
        rows = []
        for model_type in args.model_types:
            print(f"\n===== 基准 {model_type}（等级 {args.level}）=====")
            model_rows = run_model_benchmark(
                service, args.level, model_type,
                batch_sizes=tuple(args.batch_sizes),
            )
            rows.extend(model_rows)
            frame = pd.DataFrame(model_rows)
            columns = [c for c in _SUMMARY_COLUMNS if c in frame.columns]
            print(frame[columns].to_string(index=False))
        paths = save_benchmark_report(
            rows, args.out, f"benchmark_{args.level}",
            level=args.level, data_dir=data_dir,
        )
        print(f"\n报告已保存: {paths['csv'].parent} / "
              f"{paths['csv'].name[:-4]}.*(csv|json|md)")
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    main()
