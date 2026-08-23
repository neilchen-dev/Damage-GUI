"""测试共用的合成数据集与服务工厂（固定模式，无随机性）。

与 test_service.py 保持相同的生成方式，供 M1 新增测试复用，
避免跨测试模块导入。
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG  # noqa: E402
from damage_gui.data.loader import DamageDataManager  # noqa: E402
from damage_gui.model.bundle import DamageModelService  # noqa: E402

SHAPE = (64, 64)


def synthetic_matrix(h: float, v: float, deg: float) -> np.ndarray:
    """幅值随工况变化的中心高斯场（带轻微位置移动以锻炼质心对齐）。"""
    rows, cols = np.meshgrid(
        np.arange(SHAPE[0], dtype=float), np.arange(SHAPE[1], dtype=float),
        indexing="ij",
    )
    center_row = 31.5 + (h - 2.0) * 1.0
    center_col = 31.5 + (h - 2.0) * 1.5
    dr = rows - center_row
    dc = cols - center_col
    amplitude = 0.4 + 0.1 * h + 0.0002 * v + 0.004 * deg
    return np.clip(
        amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * 3.5 * 3.5)), 0.0, 1.0
    )


def write_synthetic_dataset(directory: Path) -> None:
    for h in (1.0, 2.0, 3.0):
        for v in (100.0, 200.0):
            for deg in (10.0, 20.0):
                matrix = synthetic_matrix(h, v, deg)
                name = (
                    f"DamageMatrix_F_h_{int(h * 10)}"
                    f"_v_{int(v * 10)}_deg_{int(deg * 10)}"
                )
                lines = ["synthetic_header"]
                for row in matrix:
                    lines.append("\t".join(f"{value:.6f}" for value in row))
                (directory / name).write_text(
                    "\n".join(lines) + "\n", encoding="gbk"
                )


def make_service(directory: Path) -> DamageModelService:
    config = dataclasses.replace(CONFIG, target_shape=SHAPE, eval_smoothing_sigma=1.0)
    return DamageModelService(DamageDataManager(directory), config=config)


def make_synthetic_dataset() -> tuple[tempfile.TemporaryDirectory, Path]:
    """创建临时合成数据集目录；调用方负责 cleanup()。"""
    tmp = tempfile.TemporaryDirectory()
    data_dir = Path(tmp.name)
    write_synthetic_dataset(data_dir)
    return tmp, data_dir
