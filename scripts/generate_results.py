"""Generate reproducible example metrics and a prediction figure from local data."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition, DamageDataManager, read_damage_matrix
from damage_gui.model.bundle import DamageModelService
from damage_gui.visualization.plots import render_heatmaps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--output-dir", type=Path, default=Path("examples/results"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    service = DamageModelService(DamageDataManager(args.data_dir))
    bundle = service.train_bundle(args.level)
    records = service.data_manager.get_level_records(args.level)
    test_condition = Condition(**bundle.test_conditions[0])
    record = next(item for item in records if item.condition == test_condition)
    true_matrix = read_damage_matrix(record.path)
    prediction = service.predict_matrix(bundle, test_condition)

    figure = render_heatmaps(
        true_matrix,
        prediction,
        CONFIG.display_threshold,
        CONFIG,
    )
    figure.savefig(args.output_dir / f"{args.level.lower()}_prediction.png", dpi=160)
    bundle.accuracy_report.to_csv(args.output_dir / f"{args.level.lower()}_accuracy.csv", index=False)

    focus_scope = f"damage_gt_{CONFIG.relative_error_threshold:.2f}"
    smoothed = bundle.accuracy_report
    if "field" in smoothed.columns:
        smoothed = smoothed[smoothed["field"] == "smoothed"]

    lines = [
        f"# {args.level} level evaluation result",
        "",
        "Generated from the local simulation dataset using the default seeded 80/20 split.",
        "",
        f"Representative held-out condition: `h={test_condition.h:g}, v={test_condition.v:g}, deg={test_condition.deg:g}`.",
        "",
        "| Scope | RMSE | MAE | R2 | Mean relative error | P95 hybrid error |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in smoothed.iterrows():
        if row["scope"] == "spatial":
            continue
        lines.append(
            f"| {row['scope']} | {row['RMSE']:.4f} | {row['MAE']:.4f} | {row['R2']:.4f} | "
            f"{row['MeanRelativeError']:.2%} | {row['P95HybridError']:.2%} |"
        )
    (args.output_dir / f"{args.level.lower()}_result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
