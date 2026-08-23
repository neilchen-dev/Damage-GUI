r"""扫描 POD 模态数 K，比较精度、解释方差、模型大小与性能。

用法：
    python scripts/pod_sweep.py --data-dir path\to\data --level F
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition, DamageDataManager
from damage_gui.evaluation.metrics import extract_core_metrics
from damage_gui.model.bundle import DamageModelService


def benchmark_prediction(service, bundle) -> float:
    conditions = [Condition(**item) for item in bundle.test_conditions]
    if not conditions:
        return float("nan")
    service.predict_matrix(bundle, conditions[0])  # 预热
    started = time.perf_counter()
    for condition in conditions:
        service.predict_matrix(bundle, condition)
    return (time.perf_counter() - started) / len(conditions) * 1000.0


def summarize(service, bundle, requested_k: int) -> dict[str, float | int]:
    config = bundle.resolved_config()
    mean_re, p95_hybrid = extract_core_metrics(bundle.accuracy_report, config)
    focus_scope = f"damage_gt_{config.relative_error_threshold:.2f}"
    focus = bundle.accuracy_report[
        (bundle.accuracy_report["scope"] == focus_scope)
        & (bundle.accuracy_report["field"] == "smoothed")
    ].iloc[0]
    return {
        "RequestedK": requested_k,
        "UsedK": bundle.model.n_components_used,
        "ExplainedVariance": bundle.model.explained_variance,
        "MeanRE": mean_re,
        "P95Hybrid": p95_hybrid,
        "R2": float(focus["R2"]),
        "ModelSize_MB": len(pickle.dumps(bundle.model, protocol=5)) / (1024.0**2),
        "TrainTime_s": bundle.train_time_seconds,
        "PredictTime_ms": benchmark_prediction(service, bundle),
    }


def write_markdown(frame: pd.DataFrame, output: Path, level: str) -> None:
    lines = [
        f"# {level} 级 POD 模态数扫描",
        "",
        "固定随机种子 80/20 划分；精度指标为主要毁伤区 Smoothed 口径。",
        "",
        "| K | Used K | Explained variance | Mean RE | P95 Hybrid | R² | Model (MB) | Train (s) | Predict (ms) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in frame.iterrows():
        lines.append(
            f"| {int(row['RequestedK'])} | {int(row['UsedK'])} | "
            f"{row['ExplainedVariance']:.2%} | {row['MeanRE']:.2%} | "
            f"{row['P95Hybrid']:.2%} | {row['R2']:.4f} | "
            f"{row['ModelSize_MB']:.2f} | {row['TrainTime_s']:.1f} | "
            f"{row['PredictTime_ms']:.1f} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    frame.to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--components", nargs="+", type=int, default=[5, 10, 20, 30, 50])
    parser.add_argument(
        "--output", type=Path, default=Path("examples/results/pod_sweep.md")
    )
    args = parser.parse_args()

    if any(value < 1 for value in args.components):
        parser.error("--components 中的 K 必须全部为正整数")

    service = DamageModelService(DamageDataManager(args.data_dir))
    rows = []
    for components in args.components:
        print(f"Running POD-RBF K={components} ...", flush=True)
        bundle = service.train_bundle(
            args.level,
            validation_mode="random",
            model_type="pod_rbf",
            pod_n_components=components,
        )
        rows.append(summarize(service, bundle, components))

    frame = pd.DataFrame(rows)
    print(frame.to_string(index=False))
    write_markdown(frame, args.output, args.level)
    print(f"\n结果已保存: {args.output} / {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
