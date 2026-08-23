"""数据读取：工况解析、DamageMatrix 文件扫描与读取。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from damage_gui.config import Config, CONFIG
from damage_gui.data.preprocessing import normalize_matrix_shape

FILENAME_PATTERN = re.compile(r"DamageMatrix_([FMP])_h_(\d+)_v_(\d+)_deg_(\d+)$")


@dataclass(frozen=True)
class Condition:
    h: float
    v: float
    deg: float

    def as_key(self) -> tuple[float, float, float]:
        return (round(self.h, 1), round(self.v, 1), round(self.deg, 1))

    def as_dict(self) -> dict[str, float]:
        return {"h": self.h, "v": self.v, "deg": self.deg}

    def as_array(self) -> np.ndarray:
        return np.array([self.h, self.v, self.deg], dtype=np.float64)


@dataclass(frozen=True)
class DamageRecord:
    level: str
    condition: Condition
    path: Path


class DamageDataManager:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def scan_records(self) -> list[DamageRecord]:
        if not self.data_dir.exists():
            raise FileNotFoundError(f"数据目录不存在: {self.data_dir}")

        records: list[DamageRecord] = []
        for path in sorted(self.data_dir.iterdir()):
            match = FILENAME_PATTERN.match(path.name)
            if not match:
                continue
            level, h_raw, v_raw, deg_raw = match.groups()
            condition = Condition(
                h=float(h_raw) / 10.0,
                v=float(v_raw) / 10.0,
                deg=float(deg_raw) / 10.0,
            )
            records.append(DamageRecord(level=level, condition=condition, path=path))
        if not records:
            raise FileNotFoundError(f"未在 {self.data_dir} 中找到 DamageMatrix 文件")
        return records

    def get_level_records(self, level: str) -> list[DamageRecord]:
        records = [record for record in self.scan_records() if record.level == level]
        if not records:
            raise ValueError(f"数据目录中没有等级 {level} 的矩阵文件")
        return records

    def find_record(self, level: str, condition: Condition) -> DamageRecord | None:
        target = condition.as_key()
        for record in self.get_level_records(level):
            if record.condition.as_key() == target:
                return record
        return None


def read_damage_matrix(path: Path, config: Config | None = None) -> np.ndarray:
    """读取单个 DamageMatrix 文件，统一尺寸并做双边滤波降噪。

    config 参数允许消融实验关闭降噪（denoise_radius=0）。
    """
    config = config or CONFIG
    frame = pd.read_csv(path, sep="\t", encoding="gbk", header=None, skiprows=1)
    frame = frame.dropna(axis=1, how="all")
    matrix = frame.to_numpy(dtype=np.float32)
    matrix = normalize_matrix_shape(matrix, config.target_shape)
    if config.denoise_radius > 0:
        from damage_gui.data.preprocessing import bilateral_filter

        matrix = bilateral_filter(
            matrix,
            config.denoise_sigma_spatial,
            config.denoise_sigma_range,
            config.denoise_radius,
        )
    return matrix
