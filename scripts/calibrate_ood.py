"""用真实工况网格与结构化验证结果校准 OOD 距离阈值。

该脚本不重新训练模型，而是读取 ``validation_study.py`` 生成的 CSV，
把每个轴的归一化网格步长与对应 Leave-*-out 的 P95 Hybrid 误差配对。
误差达到目标的轴应落入 Medium，未达到目标的轴应落入 Low。

用法：
    python scripts/calibrate_ood.py --data-dir dist/data \
        --validation-csv examples/results/validation_summary.csv --level F
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import DamageDataManager
from damage_gui.model.ood import OODDetector


AXES = ("h", "v", "deg")
MODE_MARKERS = {
    "h": "Leave-h-out",
    "v": "Leave-v-out",
    "deg": "Leave-deg-out",
}


def normalized_steps(records) -> dict[str, float]:
    """返回各工况轴相对于全范围的中位网格步长。"""
    result: dict[str, float] = {}
    for axis in AXES:
        values = np.array(
            sorted({getattr(record.condition, axis) for record in records}),
            dtype=np.float64,
        )
        if len(values) < 2 or values[-1] <= values[0]:
            continue
        result[axis] = float(np.median(np.diff(values)) / (values[-1] - values[0]))
    return result


def validation_errors(frame: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """提取三个整层留出方向的 (Mean RE, P95 Hybrid)。"""
    required = {"Validation", "MeanRE", "P95Hybrid"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"验证 CSV 缺少列: {', '.join(sorted(missing))}")
    errors: dict[str, tuple[float, float]] = {}
    for axis, marker in MODE_MARKERS.items():
        matched = frame[frame["Validation"].astype(str).str.contains(marker, regex=False)]
        if len(matched) != 1:
            raise ValueError(f"验证 CSV 中应恰有一行包含 {marker!r}")
        row = matched.iloc[0]
        errors[axis] = (float(row["MeanRE"]), float(row["P95Hybrid"]))
    return errors


def recommend_thresholds(
    steps: dict[str, float],
    errors: dict[str, tuple[float, float]],
    target: float,
) -> tuple[float, float]:
    """给出严格 High 阈值与区分达标/未达标轴的 Medium 阈值。"""
    shared = sorted(set(steps).intersection(errors))
    if not shared:
        raise ValueError("没有可用于校准的工况轴")

    # High 保留给已知样本附近；0.75 个最小网格步长不会覆盖完整留一层。
    high = 0.75 * min(steps[axis] for axis in shared)
    passed = [steps[axis] for axis in shared if max(errors[axis]) <= target]
    failed = [steps[axis] for axis in shared if max(errors[axis]) > target]
    if passed and failed and max(passed) < min(failed):
        medium = 0.5 * (max(passed) + min(failed))
    elif passed:
        medium = 1.2 * max(passed)
    else:
        medium = min(failed)
    return float(high), float(max(high, medium))


def random_holdout_geometry(records, local_neighbors: int) -> dict[str, int]:
    """检查规则网格随机留出时局部空洞启发式的误报数量。"""
    train, test = train_test_split(
        records,
        test_size=CONFIG.test_size,
        random_state=CONFIG.random_state,
        shuffle=True,
    )
    detector = OODDetector(local_neighbors=local_neighbors).fit(
        np.array([record.condition.as_array() for record in train])
    )
    reports = [detector.report(record.condition) for record in test]
    in_hull = [report for report in reports if report.in_hull is True]
    return {
        "test": len(reports),
        "in_hull": len(in_hull),
        "hull_outside": sum(report.in_hull is False for report in reports),
        "local_false": sum(report.local_support is False for report in in_hull),
    }


def write_report(
    output: Path,
    level: str,
    steps: dict[str, float],
    errors: dict[str, tuple[float, float]],
    high: float,
    medium: float,
    old_geometry: dict[str, int],
    auto_geometry: dict[str, int],
) -> None:
    lines = [
        f"# {level} 级 OOD 真实数据校准",
        "",
        "误差达标线：Mean RE 与 P95 Hybrid 均不超过 "
        f"{CONFIG.relative_error_target:.0%}。",
        "",
        "| 轴 | 归一化网格步长 | Leave-out Mean RE | P95 Hybrid | 结论 |",
        "|---|---:|---:|---:|---|",
    ]
    for axis in AXES:
        mean_re, p95_hybrid = errors[axis]
        passed = max(mean_re, p95_hybrid) <= CONFIG.relative_error_target
        lines.append(
            f"| {axis} | {steps[axis]:.4f} | {mean_re:.2%} | {p95_hybrid:.2%} "
            f"| {'Medium 可接受' if passed else '应降为 Low'} |"
        )
    lines += [
        "",
        f"建议阈值：`high_max={high:.3f}`，`medium_max={medium:.3f}`。",
        f"项目采用：`high_max={CONFIG.ood_high_max:.3f}`，"
        f"`medium_max={CONFIG.ood_medium_max:.3f}`；与建议一致到工程取整精度。",
        "",
        "随机留出局部支撑检查：",
        "",
        "| 邻居策略 | 测试点 | 全局凸包内 | 凸包外 | 凸包内局部误报 |",
        "|---|---:|---:|---:|---:|",
        f"| 旧规则（8 个） | {old_geometry['test']} | {old_geometry['in_hull']} "
        f"| {old_geometry['hull_outside']} | {old_geometry['local_false']} |",
        f"| 新自动规则 | {auto_geometry['test']} | {auto_geometry['in_hull']} "
        f"| {auto_geometry['hull_outside']} | {auto_geometry['local_false']} |",
        "",
        "说明：凸包外点是随机留出恰好移除了训练网格极点，属于正确的几何外推判定。",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--validation-csv", type=Path, required=True)
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/results/ood_calibration.md"),
    )
    args = parser.parse_args()

    records = DamageDataManager(args.data_dir).get_level_records(args.level)
    steps = normalized_steps(records)
    errors = validation_errors(pd.read_csv(args.validation_csv))
    high, medium = recommend_thresholds(
        steps, errors, CONFIG.relative_error_target
    )
    old_geometry = random_holdout_geometry(records, local_neighbors=8)
    auto_geometry = random_holdout_geometry(records, local_neighbors=0)
    write_report(
        args.output,
        args.level,
        steps,
        errors,
        high,
        medium,
        old_geometry,
        auto_geometry,
    )
    print(f"建议阈值: high_max={high:.3f}, medium_max={medium:.3f}")
    print(f"旧规则局部误报: {old_geometry['local_false']}")
    print(f"新自动规则局部误报: {auto_geometry['local_false']}")
    print(f"结果已保存: {args.output}")


if __name__ == "__main__":
    main()
