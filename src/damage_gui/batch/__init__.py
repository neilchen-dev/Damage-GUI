"""批量工况预测：CSV 输入校验、逐行预测与结果导出。

惰性导出（PEP 562，与 services/__init__.py 同范式）：
``import damage_gui.batch`` 不再拉起 runner → model.bundle → scipy 全链；
只有真正访问符号时才导入对应子模块。``from damage_gui.batch.runner
import ...`` 的直接子模块导入路径不受影响。
"""

__all__ = [
    "BatchReport",
    "BatchRowOutcome",
    "OUTPUT_COLUMNS",
    "ParsedBatch",
    "parse_batch_csv",
    "run_batch",
]


def __getattr__(name: str):
    """按需解析批量 API，避免包初始化拉起科学计算栈。"""
    from importlib import import_module

    modules = {
        "BatchReport": "runner",
        "BatchRowOutcome": "runner",
        "run_batch": "runner",
        "OUTPUT_COLUMNS": "schema",
        "ParsedBatch": "schema",
        "parse_batch_csv": "schema",
    }
    module_name = modules.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{module_name}"), name)
