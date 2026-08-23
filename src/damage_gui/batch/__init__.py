"""批量工况预测：CSV 输入校验、逐行预测与结果导出。"""
from damage_gui.batch.runner import BatchReport, BatchRowOutcome, run_batch
from damage_gui.batch.schema import (
    OUTPUT_COLUMNS,
    ParsedBatch,
    parse_batch_csv,
)

__all__ = [
    "BatchReport",
    "BatchRowOutcome",
    "OUTPUT_COLUMNS",
    "ParsedBatch",
    "parse_batch_csv",
    "run_batch",
]
