"""消融实验（Ablation Study）：量化各算法设计的实际贡献。

对比配置：
    1. Raw RBF            —— 无降噪、无质心对齐（基线）
    2. RBF + Denoise      —— 仅双边滤波降噪
    3. RBF + Alignment    —— 仅质心对齐
    4. RBF + Full         —— 降噪 + 对齐（当前默认）
    5. POD-RBF + Full     —— 在 4 的基础上用 POD 降阶 + 模态系数插值

所有配置使用同一固定随机种子的 80/20 划分，在相同测试工况上评估
主要毁伤区 (damage > 0.05) 的平均相对误差与 P95 混合误差。

用法：
    python scripts/ablation_study.py --data-dir path\\to\\data --level F
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

# 允许直接以 `python scripts/ablation_study.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition, DamageDataManager, read_damage_matrix
from damage_gui.data.preprocessing import evaluation_fields
from damage_gui.evaluation.metrics import metric_row
from damage_gui.model.pod import PODRBFDamageField
from damage_gui.model.rbf import RBFDamageField


def load_matrices(records, denoise: bool):
    config = CONFIG if denoise else dataclasses.replace(CONFIG, denoise_radius=0)
    conditions = np.array([r.condition.as_array() for r in records], dtype=np.float64)
    matrices = np.array(
        [read_damage_matrix(r.path, config) for r in records], dtype=np.float32
    )
    return conditions, matrices


def evaluate_focus(model, test_conditions, test_matrices):
    """主要毁伤区核心指标（Smoothed 口径）+ 预测耗时。"""
    true_parts, pred_parts = [], []
    started = time.perf_counter()
    for values, truth in zip(test_conditions, test_matrices):
        condition = Condition(*map(float, values))
        prediction = model.predict_matrix(condition)
        true_parts.append(truth)
        pred_parts.append(prediction)
    predict_time = (time.perf_counter() - started) / len(test_conditions)

    y_true, y_pred = [], []
    for truth, prediction in zip(true_parts, pred_parts):
        smoothed_true, smoothed_pred = evaluation_fields(truth, prediction, CONFIG)
        mask = smoothed_true > CONFIG.relative_error_threshold
        y_true.append(smoothed_true.ravel()[mask.ravel()])
        y_pred.append(smoothed_pred.ravel()[mask.ravel()])
    row = metric_row(
        f"damage_gt_{CONFIG.relative_error_threshold:.2f}",
        np.concatenate(y_true),
        np.concatenate(y_pred),
        CONFIG.relative_error_threshold,
        CONFIG,
    )
    return row, predict_time


def run_ablation(name: str, model, train_cond, train_mats, test_cond, test_mats):
    started = time.perf_counter()
    model.fit(train_cond, train_mats)
    train_time = time.perf_counter() - started
    row, predict_time = evaluate_focus(model, test_cond, test_mats)
    return {
        "Model": name,
        "TrainTime_s": train_time,
        "PredictTime_ms": predict_time * 1000.0,
        "MeanRE": row["MeanRelativeError"],
        "P95Hybrid": row["P95HybridError"],
        "R2": row["R2"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--level", choices=("F", "M", "P"), default="F")
    parser.add_argument("--pod-components", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("examples/results/ablation.md"))
    args = parser.parse_args()

    records = DamageDataManager(args.data_dir).get_level_records(args.level)
    train_records, test_records = train_test_split(
        records, test_size=CONFIG.test_size,
        random_state=CONFIG.random_state, shuffle=True,
    )

    # 预加载两套矩阵（降噪 / 不降噪），避免重复解析文件
    train_cond_denoised, train_mats_denoised = load_matrices(train_records, denoise=True)
    test_cond_denoised, test_mats_denoised = load_matrices(test_records, denoise=True)
    train_cond_raw, train_mats_raw = load_matrices(train_records, denoise=False)
    test_cond_raw, test_mats_raw = load_matrices(test_records, denoise=False)

    def rbf(align: bool):
        return RBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=CONFIG.target_shape, align=align,
            config=CONFIG,
        )

    results = [
        run_ablation(
            "Raw RBF", rbf(align=False),
            train_cond_raw, train_mats_raw, test_cond_raw, test_mats_raw,
        ),
        run_ablation(
            "RBF + Denoise", rbf(align=False),
            train_cond_denoised, train_mats_denoised,
            test_cond_denoised, test_mats_denoised,
        ),
        run_ablation(
            "RBF + Alignment", rbf(align=True),
            train_cond_raw, train_mats_raw, test_cond_raw, test_mats_raw,
        ),
        run_ablation(
            "RBF + Denoise + Alignment", rbf(align=True),
            train_cond_denoised, train_mats_denoised,
            test_cond_denoised, test_mats_denoised,
        ),
        run_ablation(
            f"POD-RBF(K={args.pod_components}) + Denoise + Alignment",
            PODRBFDamageField(
                kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
                target_shape=CONFIG.target_shape, align=True,
                n_components=args.pod_components,
                config=CONFIG,
            ),
            train_cond_denoised, train_mats_denoised,
            test_cond_denoised, test_mats_denoised,
        ),
    ]

    frame = pd.DataFrame(results)
    print(frame.to_string(index=False))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {args.level} 级消融实验（Ablation Study）",
        "",
        f"固定随机种子 80/20 划分（random_state={CONFIG.random_state}），"
        f"指标为主要毁伤区 (damage>{CONFIG.relative_error_threshold:g}) 的 Smoothed 口径。",
        "",
        "| Model | Alignment | Denoise | Mean RE | P95 Hybrid | R2 | Train (s) | Predict (ms) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    flags = [
        ("No", "No"), ("No", "Yes"), ("Yes", "No"), ("Yes", "Yes"), ("Yes", "Yes"),
    ]
    for (result, (align_flag, denoise_flag)) in zip(results, flags):
        lines.append(
            f"| {result['Model']} | {align_flag} | {denoise_flag} "
            f"| {result['MeanRE']:.2%} | {result['P95Hybrid']:.2%} "
            f"| {result['R2']:.4f} | {result['TrainTime_s']:.1f} "
            f"| {result['PredictTime_ms']:.0f} |"
        )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    csv_path = args.output.with_suffix(".csv")
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n结果已保存: {args.output} / {csv_path}")


if __name__ == "__main__":
    main()
