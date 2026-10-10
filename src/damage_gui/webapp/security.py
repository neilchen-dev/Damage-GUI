"""API authentication and bounded admission for expensive requests."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import threading
import time
from collections import deque
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse

COOKIE_NAME = "damagelab_session"
SESSION_SECONDS = 8 * 3600
COMPUTE_PATHS = {"/api/predict", "/api/aim", "/api/batch"}


def validate_token(token: str | None) -> str | None:
    if token is not None and (len(token) < 32 or len(token) > 512 or token != token.strip()):
        raise ValueError(
            "DAMAGE_GUI_API_TOKEN must contain 32..512 characters without surrounding whitespace"
        )
    return token


class ApiSecurityMiddleware:
    def __init__(
        self,
        app,
        *,
        token: str | None,
        context,
        max_compute: int = 2,
        max_result_bytes: int = 1024**3,
        per_minute: int = 60,
    ):
        self.app = app
        self.token = token
        self.context = context
        self.max_result_bytes = max_result_bytes
        self._slots = threading.BoundedSemaphore(max_compute)
        self._per_minute = per_minute
        self._requests = deque()
        self._rate_lock = threading.Lock()

    def _matches(self, value: str) -> bool:
        return bool(self.token) and hmac.compare_digest(value.encode(), self.token.encode())

    def _session(self) -> str:
        issued = str(int(time.time()))
        mac = hmac.new(self.token.encode(), issued.encode(), hashlib.sha256).hexdigest()
        return f"{issued}.{mac}"

    def _valid_session(self, value: str) -> bool:
        try:
            issued, mac = value.split(".", 1)
            age = time.time() - int(issued)
            expected = hmac.new(self.token.encode(), issued.encode(), hashlib.sha256).hexdigest()
            return 0 <= age < SESSION_SECONDS and hmac.compare_digest(
                mac.encode(), expected.encode()
            )
        except (ValueError, AttributeError):
            return False

    def _disk_full(self) -> bool:
        root = self.context.result_dir
        if root is None or not root.exists():
            return False
        total = 0
        for path in root.rglob("*"):
            if path.is_symlink():
                continue
            try:
                if path.is_file():
                    total += path.stat().st_size
            except FileNotFoundError:
                continue  # a concurrent upload/cleanup completed
            if total >= self.max_result_bytes:
                return True
        return False

    def _retry_after(self) -> int:
        now = time.monotonic()
        with self._rate_lock:
            while self._requests and self._requests[0] <= now - 60:
                self._requests.popleft()
            if len(self._requests) >= self._per_minute:
                return max(1, int(60 - (now - self._requests[0])) + 1)
            self._requests.append(now)
            return 0

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (
            scope.get("type") != "http"
            or not (path == "/api" or path.startswith("/api/"))
            or path == "/api/health"
        ):
            await self.app(scope, receive, send)
            return
        request = Request(scope)

        async def reject(status, detail, headers=None):
            await JSONResponse({"detail": detail}, status_code=status, headers=headers)(
                scope, receive, send
            )

        if not self.token:
            await reject(503, "服务未配置访问令牌，请设置 DAMAGE_GUI_API_TOKEN")
            return
        bearer = request.headers.get("authorization", "")
        token_ok = bearer.startswith("Bearer ") and self._matches(bearer[7:])
        cookie_ok = self._valid_session(request.cookies.get(COOKIE_NAME, ""))
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin:
                try:
                    source = urlsplit(origin)
                    same_origin = (
                        source.netloc == request.url.netloc and source.scheme == request.url.scheme
                    )
                except ValueError:
                    same_origin = False
                if not same_origin:
                    await reject(403, "请求来源无效")
                    return
        if path == "/api/session" and request.method == "POST":
            if not token_ok:
                await reject(401, "访问令牌无效", {"WWW-Authenticate": "Bearer"})
                return
            response = JSONResponse({"status": "ok"})
            response.set_cookie(
                COOKIE_NAME,
                self._session(),
                max_age=SESSION_SECONDS,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="strict",
                path="/api",
            )
            response.headers["Cache-Control"] = "no-store"
            await response(scope, receive, send)
            return
        if not token_ok and not cookie_ok:
            await reject(401, "需要访问令牌", {"WWW-Authenticate": "Bearer"})
            return
        if path == "/api/session" and request.method == "DELETE":
            response = JSONResponse({"status": "ok"})
            response.delete_cookie(COOKIE_NAME, path="/api")
            await response(scope, receive, send)
            return
        compute = request.method == "POST" and path in COMPUTE_PATHS
        if compute:
            retry_after = self._retry_after()
            if retry_after:
                await reject(429, "计算请求超过每分钟限额", {"Retry-After": str(retry_after)})
                return
            try:
                full = await asyncio.to_thread(self._disk_full)
            except OSError:
                await reject(503, "结果存储当前不可用")
                return
            if full:
                await reject(507, "结果存储已达到容量上限，请清理或增加配额")
                return
            if not self._slots.acquire(blocking=False):
                await reject(429, "计算请求过多，请稍后重试", {"Retry-After": "1"})
                return
        try:

            async def private_send(message):
                if message["type"] == "http.response.start":
                    message = dict(message)
                    message["headers"] = list(message.get("headers", [])) + [
                        (b"cache-control", b"no-store")
                    ]
                await send(message)

            await self.app(scope, receive, private_send)
        finally:
            if compute:
                self._slots.release()
