"""工程化 CLI：核心功能脱离 GUI 执行（info / predict / batch）。

用法：
    damage-gui-cli info    --model damage_model_F.joblib
    damage-gui-cli predict --model m.joblib --h 1 --v 300 --deg 30 [--export out.csv]
    damage-gui-cli batch   --model m.joblib --input in.csv --output out.csv
                           [--db damage_gui.db] [--data-dir data]

等价于 `python -m damage_gui.cli <子命令> ...`（GUI 入口 damage-gui 不变）。
退出码：0 成功；1 执行失败（含批量部分行失败）；2 输入/用法错误。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from damage_gui.data.loader import DamageDataManager
from damage_gui.errors import DataValidationError, ModelLoadError
from damage_gui.logging_setup import setup_logging
from damage_gui.model.registry import load_model
from damage_gui.services.batch_service import BatchService
from damage_gui.services.conditions import validate_condition
from damage_gui.services.export_service import export_matrix_csv
from damage_gui.services.prediction_service import PredictionService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="damage-gui-cli",
        description="Damage-GUI 命令行工具：模型信息 / 单工况预测 / 批量预测",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="查看模型元数据与训练信息")
    info.add_argument("--model", required=True, help="模型 joblib 文件路径")

    predict = subparsers.add_parser("predict", help="单工况毁伤场预测")
    predict.add_argument("--model", required=True, help="模型 joblib 文件路径")
    predict.add_argument("--h", type=float, required=True, help="高度 h (m)")
    predict.add_argument("--v", type=float, required=True, help="落速 v (m/s)")
    predict.add_argument("--deg", type=float, required=True, help="落角 deg (°)")
    predict.add_argument(
        "--export", default=None, help="可选：预测矩阵导出 CSV 路径"
    )

    batch = subparsers.add_parser("batch", help="CSV 批量预测")
    batch.add_argument("--model", required=True, help="模型 joblib 文件路径")
    batch.add_argument("--input", required=True, help="输入 CSV（job_id,h,v,deg,level）")
    batch.add_argument("--output", required=True, help="输出 CSV 路径")
    batch.add_argument("--db", default=None, help="SQLite 追溯库路径（默认自动解析）")
    batch.add_argument("--data-dir", default=None, help="训练数据目录（真值对照指标）")
    return parser


def _validate_condition(h: float, v: float, deg: float):
    """Compatibility adapter retaining the CLI's historical helper name."""
    return validate_condition(h=h, v=v, deg=deg)


def _cmd_info(args: argparse.Namespace) -> int:
    try:
        bundle = load_model(args.model)
    except ModelLoadError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    config = bundle.resolved_config()
    print(f"模型文件: {Path(args.model).name}")
    print(f"毁伤等级: {bundle.level}")
    print(f"模型类型: {getattr(bundle.model, 'model_name', bundle.model_type)}")
    print(f"训练/测试工况: {len(bundle.train_conditions)} / {len(bundle.test_conditions)}")
    print(f"验证方式: {bundle.validation_mode}")
    print(f"RBF 核: {config.rbf_kernel}（smoothing={config.rbf_smoothing}）")
    print(f"质心对齐: {'开启' if config.align_patterns else '关闭'}")

    metadata = getattr(bundle, "metadata", None)
    if metadata is None:
        print("元数据: 旧版模型（无追溯信息，建议用新版本重新训练）")
        return 0
    for line in metadata.summary_lines():
        print(line)
    return 0


def _cmd_predict(args: argparse.Namespace) -> int:
    try:
        bundle = load_model(args.model)
        condition = _validate_condition(args.h, args.v, args.deg)
    except (ModelLoadError, DataValidationError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    result = PredictionService().predict(bundle, condition)
    duration_ms = result.elapsed_ms

    config = bundle.resolved_config()
    threshold = config.eval_focus_thresholds[-1]

    print(
        f"预测完成: h={args.h:g}, v={args.v:g}, deg={args.deg:g}，"
        f"耗时 {duration_ms} ms"
    )
    print(f"峰值强度: {result.peak_intensity:.4f}")
    print(f"毁伤面积占比 (damage > {threshold:g}): {result.damage_area_ratio:.2%}")

    metadata = getattr(bundle, "metadata", None)
    if metadata is not None:
        print(f"模型: {metadata.model_id[:8]}（{metadata.model_type}，"
              f"等级 {metadata.damage_level}，软件 {metadata.app_version}）")

    if result.ood_report is not None:
        report = result.ood_report
        print(
            f"模型可信度: {report.level_label} "
            f"(最近工况距离 {report.distance:.3f})"
        )

    if args.export:
        export_matrix_csv(result.prediction, args.export, config)
        print(f"预测矩阵已导出: {args.export}")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    try:
        bundle = load_model(args.model)
        batch_service = BatchService()
        parsed = batch_service.parse_csv(args.input, default_level=bundle.level)
    except (ModelLoadError, DataValidationError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    if not parsed.rows:
        print("错误: 输入 CSV 中没有可预测的合法行", file=sys.stderr)
        return 2

    if parsed.invalid:
        print(
            f"输入校验: {len(parsed.invalid)} 行无效（将以 FAILED 记录）",
            file=sys.stderr,
        )

    data_manager = DamageDataManager(args.data_dir) if args.data_dir else None

    def progress(done: int, total: int, stage: str) -> None:
        percent = done / total * 100.0 if total else 0.0
        print(f"\r[{percent:5.1f}%] {stage}", end="", flush=True)

    report = batch_service.run(
        bundle,
        parsed,
        data_manager=data_manager,
        output_path=args.output,
        db_path=args.db,
        input_source=Path(args.input).name,
        progress=progress,
    )
    print()
    print(
        f"批量预测完成: 成功 {report.success_count}/{report.total}，"
        f"失败 {report.failed_count}，耗时 {report.duration_ms} ms"
    )
    print(f"输出 CSV: {args.output}")
    if not report.db_recorded:
        print(
            "警告: 结果未写入 SQLite 追溯数据库（已记录错误日志，"
            "计算结果不受影响）",
            file=sys.stderr,
        )
    return 0 if report.failed_count == 0 and not report.cancelled else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    setup_logging()
    handlers = {
        "info": _cmd_info,
        "predict": _cmd_predict,
        "batch": _cmd_batch,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
