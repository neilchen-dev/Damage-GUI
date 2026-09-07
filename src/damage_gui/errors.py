"""统一错误体系：GUI/CLI 展示友好消息，完整 traceback 只进日志。"""
from __future__ import annotations


class DamageGuiError(Exception):
    """项目可预期错误的公共父类。"""


class DataValidationError(DamageGuiError):
    """输入数据校验失败（批量 CSV 结构、工况参数范围等）。"""


class ModelLoadError(DamageGuiError):
    """模型文件损坏、格式不正确或元数据不兼容。"""


class ModelFitError(DamageGuiError):
    """模型训练失败（如工况重复导致的奇异/病态线性方程组）。"""


class PredictionError(DamageGuiError):
    """预测执行失败。"""


class OperationCancelled(DamageGuiError):
    """任务被用户取消（训练取消等协作式取消信号）。"""


class TaskStateError(DamageGuiError):
    """任务状态机非法转移或重复启动。"""


class LifecycleError(DamageGuiError):
    """模型生命周期登记或状态转移不合法。"""
