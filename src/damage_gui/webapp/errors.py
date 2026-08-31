"""Expected web-adapter errors and their HTTP-facing semantics."""
from __future__ import annotations


class WebAppError(Exception):
    """Base class for errors that can be safely shown to an API client."""

    status_code = 400
    public_detail = "请求无效"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.public_detail)
        self.detail = detail or self.public_detail


class InvalidIdentifierError(WebAppError):
    status_code = 400
    public_detail = "标识符格式无效"


class ModelNotFoundError(WebAppError):
    status_code = 404
    public_detail = "模型不存在"


class ModelUnavailableError(WebAppError):
    status_code = 503
    public_detail = "模型当前不可用"


class ServiceUnavailableError(WebAppError):
    status_code = 503
    public_detail = "服务当前不可用"


class JobNotFoundError(WebAppError):
    status_code = 404
    public_detail = "任务不存在"


class JobCapacityError(WebAppError):
    status_code = 429
    public_detail = "批量任务队列已满"


class JobNotReadyError(WebAppError):
    status_code = 409
    public_detail = "任务结果尚未就绪"


class JobNotCancellableError(WebAppError):
    status_code = 409
    public_detail = "该任务不支持取消"


class ResultNotFoundError(WebAppError):
    status_code = 404
    public_detail = "结果不存在或已过期"
