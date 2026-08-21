r"""运行全部结构化验证方式并生成可直接放入 README 的汇总表。

用法：
    python scripts/validation_study.py --data-dir path\to\data --level F
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import DamageDataManager
from damage_gui.evaluation.metrics import extract_core_metrics
from damage_gui.model.bundle import DamageModelService
from damage_gui.model.validation import VALIDATION_LABELS, VALIDATION_MODES


def summarize_bundle(bundle) -> dict[str, float | str]:
    config = bundle.resolved_config()
    mean_re, p95_hybrid = extract_core_metrics(bundle.accuracy_report, config)
    focus_scope = f"damage_gt_{config.relative_error_threshold:.2f}"
    focus = bundle.accuracy_report[
        (bundle.accuracy_report["scope"] == focus_scope)
        & (bundle.accuracy_report["field"] == "smoothed")
    ].iloc[0]
    spatial = bundle.accuracy_report[
        bundle.accuracy_report["scope"] == "spatial"
    ].iloc[0]
    return {
        "Validation": VALIDATION_LABELS[bundle.validation_mode],
        "MeanRE": mean_re,
        "P95Hybrid": p95_hybrid,
        "R2": float(focus["R2"]),
        "IoU": float(spatial["IoU"]),
        "Dice": float(spatial["Dice"]),
        "TrainTime_s": bundle.train_time_seconds,
    }


def write_markdown(frame: pd.DataFrame, output: Path, level: str, model_type: str) -> None:
    lines = [
        f"# {level} 级结构化验证汇总",
        "",
        f"模型：`{model_type}`；指标为主要毁伤区 Smoothed 口径，空间指标为 Raw 口径。",
        "",
        "| Validation | Mean RE | P95 Hybrid | R² | IoU | Dice | Train (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in frame.iterrows():
        lines.append(
            f"| {row['Validation']} | {row['MeanRE']:.2%} | "
            f"{row['P95Hybrid']:.2%} | {row['R2']:.4f} | "
            f"{row['IoU']:.4f} | {row['Dice']:.4f} | {row['TrainTime_s']:.1f} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    frame.to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--model-type", choices=("rbf", "pod_rbf"), default="rbf")
    parser.add_argument("--pod-components", type=int, default=CONFIG.pod_n_components)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/results/validation_summary.md"),
    )
    args = parser.parse_args()

    service = DamageModelService(DamageDataManager(args.data_dir))
    rows = []
    for mode in VALIDATION_MODES:
        print(f"Running {VALIDATION_LABELS[mode]} ...", flush=True)
        bundle = service.train_bundle(
            args.level,
            validation_mode=mode,
            model_type=args.model_type,
            pod_n_components=args.pod_components,
        )
        rows.append(summarize_bundle(bundle))

    frame = pd.DataFrame(rows)
    print(frame.to_string(index=False))
    write_markdown(frame, args.output, args.level, args.model_type)
    print(f"\n结果已保存: {args.output} / {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
