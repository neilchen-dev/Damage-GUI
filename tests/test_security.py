"""Regression coverage for the security audit's attack paths."""

from __future__ import annotations

import csv
import os
import pickle
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from damage_gui.errors import ModelLoadError
from damage_gui.model.registry import load_model
from damage_gui.model.signing import sign_existing_model, signature_path
from damage_gui.optimization.aim import (
    correlated_gaussian_kernel,
    gaussian_cell_probability_kernel,
    gaussian_sampled_probability_kernel,
)
from damage_gui.services.export_service import export_rows_csv


class TouchProbe:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return Path.touch, (self.marker,)


def test_unsigned_model_cannot_execute(tmp_path):
    marker = tmp_path / "executed"
    artifact = tmp_path / "malicious.joblib"
    artifact.write_bytes(pickle.dumps(TouchProbe(marker)))
    with pytest.raises(ModelLoadError, match="签名"):
        load_model(artifact)
    assert not marker.exists()


def test_tampered_signed_model_cannot_execute(tmp_path):
    marker = tmp_path / "executed"
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(pickle.dumps({"safe": True}))
    sign_existing_model(artifact)
    artifact.write_bytes(pickle.dumps(TouchProbe(marker)))
    with pytest.raises(ModelLoadError, match="签名不匹配"):
        load_model(artifact)
    assert not marker.exists()


def test_untrusted_signature_and_key_rejected(tmp_path, monkeypatch):
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(pickle.dumps({"safe": True}))
    sign_existing_model(artifact)
    other_key = tmp_path / "other-key"
    other_key.write_bytes(b"x" * 32)
    monkeypatch.setenv("DAMAGE_GUI_MODEL_KEY_FILE", str(other_key))
    with pytest.raises(ModelLoadError, match="签名不匹配"):
        load_model(artifact)
    signature_path(artifact).write_text("forged")
    with pytest.raises(ModelLoadError, match="签名不匹配"):
        load_model(artifact)


@pytest.mark.parametrize("sigma", [10000.0, 1e308])
@pytest.mark.parametrize("method", ["cell", "sampled", "correlated"])
def test_kernel_limit_rejects_before_allocation(sigma, method):
    with patch("damage_gui.optimization.aim.np.arange") as allocation:
        with pytest.raises(ValueError, match="内存预算"):
            if method == "cell":
                gaussian_cell_probability_kernel(sigma, sigma, 1, 1)
            elif method == "sampled":
                gaussian_sampled_probability_kernel(sigma, sigma, 1, 1)
            else:
                correlated_gaussian_kernel(sigma, sigma, 0.5, 1, 1)
        allocation.assert_not_called()


def test_csv_formula_escaping_preserves_numeric_values(tmp_path):
    values = [
        "=1+1",
        "+SUM(A1)",
        "-1+1",
        "@SUM(A1)",
        "  =1+1",
        "\t=1+1",
        "\r=1+1",
        "\n=1+1",
        "001",
        -2.5,
    ]
    path = tmp_path / "export.csv"
    export_rows_csv([{"value": value} for value in values], ["value"], path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        result = [row["value"] for row in csv.DictReader(handle)]
    assert result[:8] == ["'" + value for value in values[:8]]
    assert result[8:] == ["001", "-2.5"]


TOKEN = "test-access-token-0123456789abcdef"


@pytest.fixture
def web_app(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from damage_gui.webapp.app import create_app
    from damage_gui.webapp.dependencies import ModelManager

    monkeypatch.delenv("DAMAGE_GUI_API_TOKEN", raising=False)
    monkeypatch.delenv("DAMAGE_GUI_MAX_RESULT_BYTES", raising=False)
    app = create_app(
        api_token=TOKEN,
        db_path=tmp_path / "trace.db",
        data_dir=tmp_path,
        model_manager=ModelManager(initial_bundles={"test": SimpleNamespace(metadata=None)}),
        cleanup_interval=0.01,
        max_result_bytes=4096,
    )
    yield app
    app.state.web_jobs.shutdown()


def test_anonymous_cannot_enumerate_download_or_cancel(web_app):
    from fastapi.testclient import TestClient

    from damage_gui.storage.repositories import JobRepository

    job_id = JobRepository(web_app.state.web_context.db_path).insert_job(
        kind="batch_prediction", status="PENDING"
    )
    with TestClient(web_app) as client:
        for path in [
            "/api/history",
            "/api/models",
            f"/api/jobs/{job_id}",
            f"/api/jobs/{job_id}/result/csv",
            "/api/results/known/png",
        ]:
            assert client.get(path).status_code == 401
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 401
        assert (
            JobRepository(web_app.state.web_context.db_path).get_job(job_id)["status"] == "PENDING"
        )
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 200
        assert (
            client.get("/api/history", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )
        response = client.get("/api/history", headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"


def test_browser_session_login_logout_and_csrf(web_app):
    from fastapi.testclient import TestClient

    with TestClient(web_app, base_url="https://testserver") as client:
        assert client.post("/api/session").status_code == 401
        response = client.post("/api/session", headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert client.get("/api/models").status_code == 200
        assert (
            client.post("/api/aim", headers={"Origin": "https://evil.example"}).status_code == 403
        )
        # Authenticated downloads reach the route instead of failing auth.
        assert client.get("/api/results/missing/png").status_code == 404
        assert client.delete("/api/session").status_code == 200
        assert client.get("/api/models").status_code == 401


def test_expired_or_forged_session_rejected(web_app):
    from fastapi.testclient import TestClient

    with TestClient(web_app) as client:
        with patch("damage_gui.webapp.security.time.time", return_value=time.time() - 9 * 3600):
            client.post("/api/session", headers={"Authorization": f"Bearer {TOKEN}"})
        assert client.get("/api/models").status_code == 401
        client.cookies.clear()
        client.cookies.set("damagelab_session", "1.forged")
        assert client.get("/api/models").status_code == 401


def test_unconfigured_server_fails_closed(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from damage_gui.webapp.app import create_app

    monkeypatch.delenv("DAMAGE_GUI_API_TOKEN", raising=False)
    app = create_app(db_path=tmp_path / "trace.db", data_dir=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/history").status_code == 503
        assert client.get("/api/health").status_code == 200
    with pytest.raises(ValueError, match="32"):
        create_app(api_token="short")


def test_disk_threshold_blocks_computation(web_app):
    from fastapi.testclient import TestClient

    root = web_app.state.web_context.result_dir
    root.mkdir(parents=True, exist_ok=True)
    (root / "large.bin").write_bytes(b"x" * 4096)
    with TestClient(web_app) as client:
        for path in ["/api/predict", "/api/aim", "/api/batch"]:
            assert (
                client.post(path, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 507
            )
        assert (
            client.get("/api/history", headers={"Authorization": f"Bearer {TOKEN}"}).status_code
            == 200
        )


def test_periodic_retention_runs_without_restart(web_app):
    from fastapi.testclient import TestClient

    root = web_app.state.web_context.result_dir
    with TestClient(web_app):
        artifact = root / "predictions" / "old-run"
        artifact.mkdir(parents=True)
        (artifact / "prediction.npy").write_bytes(b"old")
        batch = root / "batches" / "old.csv"
        batch.parent.mkdir(parents=True, exist_ok=True)
        batch.write_bytes(b"old")
        old = time.time() - 8 * 86400
        os.utime(artifact, (old, old))
        os.utime(batch, (old, old))
        deadline = time.monotonic() + 3
        while (artifact.exists() or batch.exists()) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not artifact.exists() and not batch.exists()


def test_model_replacement_after_verification_does_not_execute(tmp_path):
    from damage_gui.model.signing import verify_model

    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(pickle.dumps({"safe": True}))
    sign_existing_model(artifact)
    marker = tmp_path / "executed"

    def replace_after_verify(path, content):
        verify_model(path, content)
        path.write_bytes(pickle.dumps(TouchProbe(marker)))

    with patch("damage_gui.model.registry.verify_model", side_effect=replace_after_verify):
        with pytest.raises(ModelLoadError, match="不是 ModelBundle"):
            load_model(artifact)
    assert not marker.exists()


def test_compute_concurrency_is_bounded_and_slots_are_released():
    import asyncio

    from damage_gui.webapp.security import ApiSecurityMiddleware

    async def exercise():
        release = asyncio.Event()
        started = asyncio.Event()
        count = 0

        async def downstream(scope, receive, send):
            nonlocal count
            count += 1
            if count == 2:
                started.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = ApiSecurityMiddleware(
            downstream, token=TOKEN, context=SimpleNamespace(result_dir=None)
        )
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/predict",
            "headers": [(b"authorization", f"Bearer {TOKEN}".encode())],
        }
        messages = []

        async def send(message):
            messages.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        first = asyncio.create_task(middleware(scope, receive, send))
        second = asyncio.create_task(middleware(scope, receive, send))
        await asyncio.wait_for(started.wait(), timeout=2)
        await middleware(scope, receive, send)
        assert any(message.get("status") == 429 for message in messages)
        assert count == 2
        release.set()
        await asyncio.gather(first, second)
        await middleware(scope, receive, send)
        assert count == 3

    asyncio.run(exercise())


def test_active_batch_output_is_excluded_from_retention(web_app):
    manager = web_app.state.web_jobs
    path = manager.batch_output_path("active")
    path.write_bytes(b"running")
    old = time.time() - 8 * 86400
    os.utime(path, (old, old))
    with manager._lock:
        manager._jobs["active"] = SimpleNamespace(output_path=path, cancel_event=threading.Event())
    try:
        manager._cleanup_old_batch_artifacts()
        assert path.exists()
    finally:
        manager._jobs.pop("active")


def test_production_startup_requires_access_token(monkeypatch):
    from damage_gui.webapp.startup import validate_startup

    monkeypatch.delenv("DAMAGE_GUI_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DAMAGE_GUI_API_TOKEN"):
        validate_startup()


def test_compute_rate_limit_recovers_after_window():
    from damage_gui.webapp.security import ApiSecurityMiddleware

    middleware = ApiSecurityMiddleware(
        None, token=TOKEN, context=SimpleNamespace(result_dir=None), per_minute=1
    )
    with patch("damage_gui.webapp.security.time.monotonic", return_value=100):
        assert middleware._retry_after() == 0
        assert middleware._retry_after() > 0
    with patch("damage_gui.webapp.security.time.monotonic", return_value=161):
        assert middleware._retry_after() == 0
