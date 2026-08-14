"""Generate reproducible example metrics and a prediction figure from local data."""
from __future__ import annotations

import argparse
from pathlib import Path

from damage_gui.app import (
    CONFIG,
    Condition,
    DamageDataManager,
    DamageModelService,
    read_damage_matrix,
    render_heatmaps,
)


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

    figure = render_heatmaps(true_matrix, prediction, CONFIG.eval_area_threshold)
    figure.savefig(args.output_dir / f"{args.level.lower()}_prediction.png", dpi=160)
    bundle.accuracy_report.to_csv(args.output_dir / f"{args.level.lower()}_accuracy.csv", index=False)

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
    for _, row in bundle.accuracy_report.iterrows():
        lines.append(
            f"| {row['scope']} | {row['RMSE']:.4f} | {row['MAE']:.4f} | {row['R2']:.4f} | "
            f"{row['MeanRelativeError']:.2%} | {row['P95HybridError']:.2%} |"
        )
    (args.output_dir / f"{args.level.lower()}_result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
