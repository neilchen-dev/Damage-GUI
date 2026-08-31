"""FastAPI application factory and optional ``damage-gui-web`` entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from damage_gui import __version__
from damage_gui.errors import DataValidationError
from damage_gui.storage.db import resolve_db_path
from damage_gui.webapp.dependencies import ModelManager, ResultStore, WebContext
from damage_gui.webapp.errors import WebAppError
from damage_gui.webapp.jobs import WebJobManager
from damage_gui.webapp.settings import WebRuntimeSettings

try:
    from fastapi import FastAPI, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # optional dependency; desktop/CLI installs remain independent
    FastAPI = None  # type: ignore[assignment,misc]
    Request = object  # type: ignore[assignment,misc]
    RequestValidationError = Exception  # type: ignore[assignment,misc,assignment]
    FileResponse = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]
    StaticFiles = None  # type: ignore[assignment,misc]

logger = logging.getLogger("damage_gui.web")
MAX_REQUEST_BYTES = 64 * 1024


class _RequestTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    """Reject oversized JSON requests before they reach domain services."""

    def __init__(self, app, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._send_too_large(scope, receive, send)
                    return
            except ValueError:
                await self._send_too_large(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await self._send_too_large(scope, receive, send)

    async def _send_too_large(self, scope, receive, send) -> None:
        response = JSONResponse(status_code=413, content={"detail": "请求体过大"})
        await response(scope, receive, send)


def create_app(
    *,
    model_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    default_model_id: str | None = None,
    model_manager: ModelManager | None = None,
    result_store: ResultStore | None = None,
) -> FastAPI:
    """Create the independent web application without creating a Tk root."""
    if FastAPI is None:
        raise RuntimeError(
            "Web dependencies are not installed; install damage-gui[web] to use FastAPI"
        )

    settings = WebRuntimeSettings.from_env()
    resolved_model_dir = Path(model_dir).resolve() if model_dir is not None else settings.model_dir
    resolved_db_path = (
        resolve_db_path(db_path) if db_path is not None else settings.db_path
    )
    resolved_data_dir = (
        Path(data_dir).resolve() if data_dir is not None else settings.data_dir
    )
    configured_result_dir = os.environ.get("DAMAGE_GUI_RESULT_DIR") or os.environ.get(
        "DAMAGE_GUI_WEB_RESULT_DIR"
    )
    result_dir = (
        Path(configured_result_dir).resolve()
        if configured_result_dir
        else (
            resolved_data_dir / "web-results"
            if resolved_data_dir is not None
            else settings.result_dir
        )
    )
    effective_result_store = result_store or ResultStore(
        result_dir=result_dir,
        retention_days=settings.retention_days,
    )
    context_result_dir = effective_result_store.result_dir or result_dir
    context = WebContext(
        model_manager=model_manager or ModelManager(
            resolved_model_dir,
            default_model_id=default_model_id or settings.default_model_id,
        ),
        result_store=effective_result_store,
        db_path=resolved_db_path,
        data_dir=Path(resolved_data_dir).resolve() if resolved_data_dir else None,
        result_dir=context_result_dir,
        retention_days=settings.retention_days,
    )

    web_jobs = WebJobManager(context)

    @asynccontextmanager
    async def lifespan(_application):
        try:
            yield
        finally:
            web_jobs.shutdown()

    application = FastAPI(
        title="Damage GUI Web API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.state.web_context = context
    application.state.web_jobs = web_jobs
    application.add_middleware(RequestSizeLimitMiddleware)

    # The Workbench is a static, same-origin client of this API.  Keeping the
    # assets here means the optional web extra remains a single deployable
    # Python application with no separate frontend server requirement.
    static_dir = Path(__file__).with_name("static")
    application.mount(
        "/static",
        StaticFiles(directory=str(static_dir)),
        name="static",
    )

    @application.get("/", include_in_schema=False)
    async def workbench_index():
        return FileResponse(static_dir / "index.html")

    from damage_gui.webapp.routes.aim import router as aim_router
    from damage_gui.webapp.routes.health import router as health_router
    from damage_gui.webapp.routes.history import router as history_router
    from damage_gui.webapp.routes.jobs import router as jobs_router
    from damage_gui.webapp.routes.models import router as models_router
    from damage_gui.webapp.routes.prediction import router as prediction_router
    from damage_gui.webapp.routes.results import router as results_router

    for router in (
        health_router,
        models_router,
        prediction_router,
        aim_router,
        history_router,
        jobs_router,
        results_router,
    ):
        application.include_router(router)

    @application.exception_handler(WebAppError)
    async def web_error_handler(_request: Request, exc: WebAppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.exception_handler(DataValidationError)
    async def data_validation_error_handler(_request: Request, exc: DataValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(ValueError)
    async def value_error_handler(_request: Request, _exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": "请求参数校验失败"})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, _exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "请求参数校验失败"})

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled web request failure", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    return application


# Uvicorn can run ``damage_gui.webapp.app:app``.  Construction is lightweight:
# no model is loaded, no database scan is performed, and Tk is never imported.
app = create_app() if FastAPI is not None else None


def main() -> None:
    """Run the optional production web entrypoint."""
    if FastAPI is None:
        raise RuntimeError("Install damage-gui[web] before running damage-gui-web")
    import uvicorn

    from damage_gui.webapp.startup import validate_startup

    settings = validate_startup()
    uvicorn.run(
        "damage_gui.webapp.app:app",
        host=settings.host,
        port=settings.port,
        workers=1,
        reload=False,
    )
