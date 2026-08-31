"""批量预测 CSV 输入/输出格式定义与解析校验。

校验分两级：
- 文件级（列缺失、文件不可读、无数据行）→ DataValidationError，整个批次拒绝；
- 行级（数值非法、超出工况范围）→ 记为 invalid 行，由 runner 转成
  FAILED 结果行，不阻断其余行的预测。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from damage_gui.errors import DataValidationError
from damage_gui.services.conditions import validate_condition

REQUIRED_INPUT_COLUMNS = ("h", "v", "deg")
OPTIONAL_INPUT_COLUMNS = ("job_id", "level")

OUTPUT_COLUMNS = (
    "job_id", "level", "h", "v", "deg", "status",
    "model_id", "model_version",
    "ood_level", "ood_distance",
    "peak_intensity", "damage_area_ratio",
    "mean_relative_error", "p95_hybrid_error",
    "duration_ms", "error_message",
)


@dataclass(frozen=True)
class BatchRowInput:
    """一条合法的批量预测输入。"""

    job_id: str
    h: float
    v: float
    deg: float
    level: str


@dataclass(frozen=True)
class InvalidBatchRow:
    """一条校验失败的输入行（保留行号与原始 job_id 便于定位）。"""

    line_no: int
    job_id: str
    error: str


@dataclass
class ParsedBatch:
    rows: list[BatchRowInput]
    invalid: list[InvalidBatchRow]

    @property
    def total(self) -> int:
        return len(self.rows) + len(self.invalid)


def parse_batch_csv(
    path: str | Path, default_level: str = "F"
) -> ParsedBatch:
    """解析并校验批量预测输入 CSV。

    必需列：h, v, deg；可选列：job_id（缺省自动编号）、level（缺省用
    default_level，即当前模型等级）。
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise DataValidationError(f"批量输入文件不存在: {csv_path.name}")
    try:
        # dtype=str 保留 job_id 前导零等原始文本；数值列随后自行 float() 转换
        frame = pd.read_csv(csv_path, dtype=str)
    except Exception as exc:  # noqa: BLE001 —— pandas 解析错误统一转译
        raise DataValidationError(
            f"批量输入 CSV 无法解析: {csv_path.name}（{exc}）"
        ) from exc

    frame.columns = [str(col).strip().lower() for col in frame.columns]
    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in frame.columns]
    if missing:
        raise DataValidationError(
            f"批量输入 CSV 缺少必需列 {missing}，实际列为 {list(frame.columns)}"
        )
    if frame.empty:
        raise DataValidationError(f"批量输入 CSV 没有数据行: {csv_path.name}")

    rows: list[BatchRowInput] = []
    invalid: list[InvalidBatchRow] = []
    for index, record in frame.iterrows():
        line_no = int(index) + 2  # +1 表头、+1 转 1 基行号
        raw_job_id = record.get("job_id")
        job_id = (
            str(raw_job_id).strip() if pd.notna(raw_job_id) and str(raw_job_id).strip()
            else f"{index + 1:04d}"
        )
        try:
            level = str(
                record["level"] if "level" in frame.columns
                and pd.notna(record.get("level"))
                and str(record.get("level")).strip()
                else default_level
            ).strip().upper()
            if level not in ("F", "M", "P"):
                raise ValueError(f"level={level} 不是有效的毁伤等级（F/M/P）")
            values = {
                name: float(record[name]) for name in REQUIRED_INPUT_COLUMNS
            }
            validate_condition(**values)
            rows.append(
                BatchRowInput(job_id=job_id, level=level, **values)
            )
        except (DataValidationError, TypeError, ValueError) as exc:
            invalid.append(
                InvalidBatchRow(line_no=line_no, job_id=job_id, error=str(exc))
            )
    return ParsedBatch(rows=rows, invalid=invalid)
