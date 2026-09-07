"""性能基准测量（M3.3）。

对每个模型类型测量三类数字，全部复用现有训练与持久化 API，
不引入第二套实现：

- 训练：墙钟时间 + Python 级峰值内存（tracemalloc，覆盖 numpy 分配）；
- 产物：joblib 模型文件大小 + 冷加载耗时；
- 推理：批量 10/100/1000 次单工况预测的 mean / median / P95 延迟
  与吞吐。cold = 加载后第一次预测（含所有首次成本，只测一次）；
  warm = 预热后的稳定统计。

内存口径说明：tracemalloc 统计的是 Python 分配器视角的峰值，
不是操作系统进程 RSS，报告中须如实标注。
"""
from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from damage_gui.data.loader import Condition
from damage_gui.model.bundle import DamageModelService, ModelBundle
from damage_gui.model.registry import load_model, save_model


def benchmark_training(
    service: DamageModelService,
    level: str,
    model_type: str,
    *,
    pod_n_components: int | None = None,
) -> dict[str, Any]:
    """训练一次并测量墙钟时间与 Python 级峰值内存。"""
    tracemalloc.start()
    try:
        started = time.perf_counter()
        bundle = service.train_bundle(
            level, model_type=model_type, pod_n_components=pod_n_components
        )
        train_time = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "model_type": model_type,
        "train_time_seconds": train_time,
        "peak_memory_mb": peak_bytes / (1024 * 1024),
        "bundle": bundle,
    }


def save_and_measure(bundle: ModelBundle, path: str | Path) -> dict[str, Any]:
    """保存模型包，测量产物大小与冷加载耗时。"""
    path = save_model(bundle, path)
    artifact_bytes = Path(path).stat().st_size
    started = time.perf_counter()
    loaded = load_model(path)
    load_time = time.perf_counter() - started
    return {
        "artifact_bytes": artifact_bytes,
        "load_time_seconds": load_time,
        "loaded": loaded,
    }


def cycle_conditions(train_conditions: list[dict[str, float]], n: int) -> list[Condition]:
    """从训练工况确定性循环生成 n 个查询工况（无需随机种子）。"""
    pool = [Condition(**item) for item in train_conditions]
    return [pool[i % len(pool)] for i in range(n)]


def latency_stats(latencies_seconds: list[float]) -> dict[str, float]:
    arr_ms = np.asarray(latencies_seconds, dtype=np.float64) * 1000.0
    total_s = float(arr_ms.sum()) / 1000.0
    return {
        "mean_ms": float(arr_ms.mean()),
        "median_ms": float(np.median(arr_ms)),
        "p95_ms": float(np.percentile(arr_ms, 95)),
        "throughput_per_s": len(arr_ms) / total_s if total_s > 0 else 0.0,
    }


def measure_inference(
    model: Any,
    conditions: list[Condition],
    batch_sizes: tuple[int, ...] = (10, 100, 1000),
    warmup: int = 1,
) -> list[dict[str, Any]]:
    """cold（加载后首次预测）+ 各批量下的 warm 延迟统计。"""
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    model.predict_matrix(conditions[0])
    rows.append(
        {"batch_size": 1, "mode": "cold", **latency_stats([time.perf_counter() - started])}
    )
    for _ in range(warmup):
        model.predict_matrix(conditions[0])
    for size in batch_sizes:
        latencies: list[float] = []
        for i in range(size):
            condition = conditions[i % len(conditions)]
            t0 = time.perf_counter()
            model.predict_matrix(condition)
            latencies.append(time.perf_counter() - t0)
        rows.append({"batch_size": size, "mode": "warm", **latency_stats(latencies)})
    return rows


def run_model_benchmark(
    service: DamageModelService,
    level: str,
    model_type: str,
    *,
    batch_sizes: tuple[int, ...] = (10, 100, 1000),
    warmup: int = 1,
    work_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """单个模型类型的完整基准：训练 + 产物 + 冷/热推理，逐批量一行。"""
    training = benchmark_training(service, level, model_type)
    bundle: ModelBundle = training["bundle"]

    def run(artifact_dir: Path) -> list[dict[str, Any]]:
        artifact = save_and_measure(bundle, artifact_dir / f"bench_{level}_{model_type}.joblib")
        conditions = cycle_conditions(bundle.train_conditions, max(batch_sizes))
        inference = measure_inference(
            artifact["loaded"].model, conditions, batch_sizes, warmup
        )
        metadata = bundle.metadata
        base = {
            "level": level,
            "model_type": model_type,
            "train_time_seconds": training["train_time_seconds"],
            "peak_memory_mb": training["peak_memory_mb"],
            "artifact_bytes": artifact["artifact_bytes"],
            "load_time_seconds": artifact["load_time_seconds"],
            "training_samples": len(bundle.train_conditions),
            "git_commit": getattr(metadata, "code_commit", None),
            "training_data_hash": getattr(metadata, "training_data_hash", None),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return [{**base, **row} for row in inference]

    if work_dir is not None:
        return run(Path(work_dir))
    with tempfile.TemporaryDirectory() as tmp:
        return run(Path(tmp))


# ===================== 报告输出 =====================

_MD_COLUMNS = (
    ("model_type", "Model"),
    ("mode", "Mode"),
    ("batch_size", "Batch"),
    ("mean_ms", "Mean(ms)"),
    ("median_ms", "Median(ms)"),
    ("p95_ms", "P95(ms)"),
    ("throughput_per_s", "Thr(/s)"),
    ("train_time_seconds", "Train(s)"),
    ("peak_memory_mb", "PeakMem(MB)"),
    ("artifact_bytes", "Artifact(B)"),
    ("load_time_seconds", "Load(s)"),
)


def save_benchmark_report(
    rows: list[dict[str, Any]],
    out_dir: str | Path,
    name: str,
    *,
    level: str | None = None,
    data_dir: str | Path | None = None,
) -> dict[str, Path]:
    """写出 CSV（全量）+ JSON（机器可读）+ Markdown（摘要表）。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)

    csv_path = out / f"{name}.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "name": name,
        "level": level or (rows[0].get("level") if rows else None),
        "data_dir": None if data_dir is None else str(data_dir),
        "generated_at": generated_at,
        "n_rows": len(rows),
        "results": rows,
    }
    json_path = out / f"{name}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# 性能基准报告：{name}",
        "",
        f"- 生成时间（UTC）: {generated_at}",
        f"- 数据目录: {payload['data_dir'] or '—'} | 等级: {payload['level'] or '—'}",
        "- 内存口径: Python 级峰值（tracemalloc），非进程 RSS",
        "- cold = 模型加载后第一次预测；warm = 预热后统计",
        "",
    ]
    if rows:
        header = " | ".join(title for _key, title in _MD_COLUMNS)
        lines += [f"| {header} |", "|" + "---|" * len(_MD_COLUMNS)]
        for row in rows:
            cells = []
            for key, _title in _MD_COLUMNS:
                value = row.get(key)
                if value is None:
                    cells.append("—")
                elif isinstance(value, float):
                    cells.append(f"{value:.4g}")
                else:
                    cells.append(str(value))
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append("（无基准结果）")
    md_path = out / f"{name}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"csv": csv_path, "json": json_path, "md": md_path}
