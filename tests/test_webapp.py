"""Phase 4 FastAPI adapter tests, including cross-layer numerical checks."""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fastapi.testclient import TestClient
except ImportError:  # optional web extra is intentionally not a desktop dependency
    TestClient = None  # type: ignore[assignment,misc]

from damage_gui.services.conditions import validate_condition
from damage_gui.services.prediction_service import PredictionService
from damage_gui.storage.repositories import JobRepository
from damage_gui.webapp.app import create_app
from damage_gui.webapp.dependencies import ModelManager
from damage_gui.webapp.errors import JobCapacityError
from damage_gui.webapp.jobs import WebJobManager
from damage_gui.webapp.routes.jobs import MAX_BATCH_BYTES, MAX_BATCH_ROWS
from synthetic_data import make_service, write_synthetic_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(TestClient is not None, "install damage-gui[web] to run web tests")
class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._runtime_dir = PROJECT_ROOT / ".test-web-runtime"
        cls.data_dir = cls._runtime_dir / "data"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        write_synthetic_dataset(cls.data_dir)
        cls.model_service = make_service(cls.data_dir)
        cls.bundle = cls.model_service.train_bundle("F", validation_mode="random", model_type="rbf")
        cls.db_path = cls._runtime_dir / "trace.db"
        if cls.db_path.exists():
            cls.db_path.unlink()
        manager = ModelManager(initial_bundles={"test-model": cls.bundle})
        cls.app = create_app(
            model_manager=manager,
            db_path=cls.db_path,
            data_dir=cls.data_dir,
        )
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._runtime_dir, ignore_errors=True)

    def test_health_and_model_metadata_do_not_load_artifact_path(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["model_ready"])
        models = self.client.get("/api/models")
        self.assertEqual(models.status_code, 200)
        body = models.json()
        self.assertEqual(body[0]["model_id"], "test-model")
        self.assertNotIn("path", body[0])
        detail = self.client.get("/api/models/test-model")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("model", detail.json())

    def test_workbench_assets_are_served_and_bound_to_real_api_routes(self) -> None:
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("DamageLab", page.text)
        self.assertIn("/static/app.js", page.text)
        css = self.client.get("/static/styles.css")
        javascript = self.client.get("/static/app.js")
        self.assertEqual(css.status_code, 200)
        self.assertEqual(javascript.status_code, 200)
        self.assertIn("--nav-width", css.text)
        for route in (
            "/api/health", "/api/models", "/api/predict", "/api/aim",
            "/api/batch", "/api/jobs/", "/api/history",
        ):
            self.assertIn(route, javascript.text)
        self.assertIn("prediction.links.png", javascript.text)
        self.assertIn("prediction.links.csv", javascript.text)
        self.assertNotIn("impact_tests_2026A", javascript.text)

    def test_disk_model_discovery_is_metadata_only_and_loader_is_cached(self) -> None:
        model_dir = self._runtime_dir / "models"
        model_dir.mkdir(exist_ok=True)
        artifact = model_dir / "server-model.joblib"
        artifact.write_bytes(b"server-owned-artifact")
        metadata = {
            "model_id": "server-model",
            "created_at": "2026-08-31T00:00:00+00:00",
            "app_version": "2.1.0",
            "schema_version": 1,
            "model_format_version": 1,
            "model_type": "rbf",
            "damage_level": "F",
            "training_samples": 12,
            "training_data_hash": "sha256:test",
            "code_commit": None,
            "parameters": {},
            "validation": {},
        }
        (model_dir / "server-model.meta.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
        loaded_paths: list[Path] = []
        manager = ModelManager(
            model_dir,
            loader=lambda path: loaded_paths.append(path) or self.bundle,
        )
        descriptor = manager.get_descriptor("server-model")
        self.assertEqual(descriptor.metadata["model_type"], "rbf")
        self.assertEqual(loaded_paths, [])
        manager.get_bundle("server-model")
        manager.get_bundle("server-model")
        self.assertEqual(loaded_paths, [artifact.resolve()])

    def test_prediction_matches_shared_service_and_result_exports(self) -> None:
        condition = self.bundle.train_conditions[0]
        expected = PredictionService(
            self.model_service.data_manager,
            model_service=self.model_service,
        ).predict(self.bundle, validate_condition(**condition))
        response = self.client.post(
            "/api/predict",
            json={**condition, "model_id": "test-model"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["condition"], condition)
        self.assertAlmostEqual(body["peak_intensity"], expected.peak_intensity)
        self.assertAlmostEqual(body["damage_area_ratio"], expected.damage_area_ratio)
        self.assertEqual(body["confidence"], expected.confidence)
        self.assertIn("MeanRelativeError", body["metrics"])

        run_id = body["run_id"]
        structured = self.client.get(f"/api/results/{run_id}")
        self.assertEqual(structured.status_code, 200)
        png = self.client.get(f"/api/results/{run_id}/png")
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png.headers["content-type"], "image/png")
        self.assertGreater(len(png.content), 1000)
        csv = self.client.get(f"/api/results/{run_id}/csv")
        self.assertEqual(csv.status_code, 200)
        self.assertTrue(csv.content.startswith(b"\xef\xbb\xbf"))
        self.assertGreater(len(csv.content), 100)

        restarted = create_app(
            model_manager=ModelManager(initial_bundles={"test-model": self.bundle}),
            db_path=self.db_path,
            data_dir=self.data_dir,
        )
        restarted_client = TestClient(restarted)
        reopened = restarted_client.get(f"/api/results/{run_id}")
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.json()["run_id"], run_id)
        reopened_png = restarted_client.get(f"/api/results/{run_id}/png")
        self.assertEqual(reopened_png.status_code, 200)
        self.assertGreater(len(reopened_png.content), 1000)

    def test_prediction_invalid_ood_aim_and_result_security(self) -> None:
        invalid = self.client.post("/api/predict", json={"h": 500.1, "v": 100, "deg": 10})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("Traceback", invalid.text)
        unexpected = self.client.post(
            "/api/predict", json={"h": 1, "v": 100, "deg": 10, "unexpected": 1}
        )
        self.assertEqual(unexpected.status_code, 422)

        ood = self.client.post(
            "/api/predict", json={"h": 500, "v": 1000, "deg": 90, "model_id": "test-model"}
        )
        self.assertEqual(ood.status_code, 200, ood.text)
        self.assertTrue(ood.json()["ood"]["is_extrapolation"])
        run_id = ood.json()["run_id"]
        aim = self.client.post(
            "/api/aim", json={"run_id": run_id, "spread_mode": "CEP", "cep": 2.0}
        )
        self.assertEqual(aim.status_code, 200, aim.text)
        self.assertEqual(tuple(aim.json()["value_field_shape"]), (64, 64))
        self.assertIsNotNone(aim.json()["job_id"])
        aim_result = self.client.get(f"/api/jobs/{aim.json()['job_id']}/result")
        self.assertEqual(aim_result.status_code, 200)
        self.assertEqual(aim_result.json()["type"], "aim")
        bad_aim = self.client.post(
            "/api/aim", json={"run_id": run_id, "spread_mode": "REP_DEP", "rho": 1.0}
        )
        self.assertEqual(bad_aim.status_code, 422)

        for path in (
            "/api/results/not-a-real-run",
            "/api/results/../../secrets",
            "/api/models/../../secrets",
        ):
            response = self.client.get(path)
            self.assertIn(response.status_code, (400, 404))
            self.assertNotIn("Traceback", response.text)

    def test_history_is_paginated_and_uses_existing_sqlite_traceability(self) -> None:
        repo = JobRepository(self.db_path)
        before = repo.count_jobs() or 0
        first = repo.insert_job(kind="training")
        second = repo.insert_job(kind="batch_prediction")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        response = self.client.get("/api/history?limit=1&offset=0")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], before + 2)
        self.assertEqual(body["limit"], 1)
        self.assertEqual(len(body["items"]), 1)

    def _wait_for_job(self, job_id: str, *, timeout: float = 15.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            if body["state"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                return body
            time.sleep(0.03)
        self.fail(f"web batch job {job_id} did not reach a terminal state")

    def test_batch_job_lifecycle_and_result_download(self) -> None:
        csv = b"job_id,h,v,deg,level\n001,2,200,10,F\n002,2,120,12,F\n"
        submitted = self.client.post(
            "/api/batch?model_id=test-model",
            content=csv,
            headers={"content-type": "text/csv", "x-filename": "batch-input.csv"},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        job_id = submitted.json()["job_id"]
        self.assertEqual(submitted.json()["type"], "batch_prediction")
        completed = self._wait_for_job(job_id)
        self.assertEqual(completed["state"], "SUCCEEDED")
        self.assertEqual(completed["completed"], 2)
        self.assertEqual(completed["total"], 2)
        result = self.client.get(f"/api/jobs/{job_id}/result")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["summary"]["success_count"], 2)
        output = self.client.get(f"/api/jobs/{job_id}/result/csv")
        self.assertEqual(output.status_code, 200, output.text)
        self.assertTrue(output.content.startswith(b"\xef\xbb\xbf"))
        history = self.client.get("/api/history?limit=100")
        self.assertIn("batch_prediction", {item["kind"] for item in history.json()["items"]})

    def test_existing_jobs_schema_migrates_for_prediction_and_aim_kinds(self) -> None:
        legacy_db = self._runtime_dir / "legacy.db"
        if legacy_db.exists():
            legacy_db.unlink()
        with sqlite3.connect(legacy_db) as connection:
            connection.executescript(
                """
                CREATE TABLE models (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, app_version TEXT NOT NULL,
                    model_type TEXT NOT NULL, damage_level TEXT NOT NULL,
                    training_samples INTEGER NOT NULL, training_data_hash TEXT NOT NULL,
                    code_commit TEXT, parameters_json TEXT NOT NULL,
                    validation_json TEXT NOT NULL, artifact_path TEXT
                );
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('training', 'batch_prediction')),
                    status TEXT NOT NULL CHECK (status IN
                        ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')),
                    model_id TEXT REFERENCES models(id), input_source TEXT,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    duration_ms INTEGER, error_summary TEXT, details_json TEXT
                );
                """
            )
        repository = JobRepository(legacy_db)
        self.assertIsNotNone(repository.insert_job(kind="prediction"))
        self.assertIsNotNone(repository.insert_job(kind="aim"))
        kinds = {row["kind"] for row in (repository.list_jobs() or [])}
        self.assertEqual(kinds, {"prediction", "aim"})

    def test_web_jobs_are_recovered_after_process_restart(self) -> None:
        stale_id = JobRepository(self.db_path).insert_job(
            kind="batch_prediction",
            status="PENDING",
            details={"web_job": True, "result_kind": "batch"},
        )
        self.assertIsNotNone(stale_id)
        restarted = create_app(
            model_manager=ModelManager(initial_bundles={"test-model": self.bundle}),
            db_path=self.db_path,
            data_dir=self.data_dir,
        )
        try:
            recovered = JobRepository(self.db_path).get_job(stale_id)
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered["status"], "FAILED")
            self.assertIn("重启", recovered["error_summary"])
        finally:
            restarted.state.web_jobs.shutdown()

    def test_batch_limits_filename_safety_and_row_failure(self) -> None:
        unsafe_name = self.client.post(
            "/api/batch?model_id=test-model",
            content=b"h,v,deg\n2,200,10\n",
            headers={"content-type": "text/csv", "x-filename": "..\\secret.csv"},
        )
        self.assertEqual(unsafe_name.status_code, 422)

        oversized = self.client.post(
            "/api/batch?model_id=test-model",
            content=b"x" * (MAX_BATCH_BYTES + 1),
            headers={"content-type": "text/csv", "x-filename": "large.csv"},
        )
        self.assertEqual(oversized.status_code, 413)

        rows = "job_id,h,v,deg,level\n" + "".join(
            f"{index},2,200,10,F\n" for index in range(MAX_BATCH_ROWS + 1)
        )
        too_many = self.client.post(
            "/api/batch?model_id=test-model",
            content=rows.encode(),
            headers={"content-type": "text/csv", "x-filename": "too-many.csv"},
        )
        self.assertEqual(too_many.status_code, 422, too_many.text)

        failed = self.client.post(
            "/api/batch?model_id=test-model",
            content=b"job_id,h,v,deg,level\n001,2,200,10,F\n002,2,200,10,M\n",
            headers={"content-type": "text/csv", "x-filename": "row-failure.csv"},
        )
        self.assertEqual(failed.status_code, 200, failed.text)
        failed_job = self._wait_for_job(failed.json()["job_id"])
        self.assertEqual(failed_job["state"], "FAILED")
        failed_result = self.client.get(
            f"/api/jobs/{failed.json()['job_id']}/result"
        )
        self.assertEqual(failed_result.status_code, 200)
        self.assertEqual(failed_result.json()["summary"]["failed_count"], 1)

    def test_batch_cancel_is_cooperative_and_terminal(self) -> None:
        csv = "job_id,h,v,deg,level\n" + "".join(
            f"{index},2,200,10,F\n" for index in range(MAX_BATCH_ROWS)
        )
        submitted = self.client.post(
            "/api/batch?model_id=test-model",
            content=csv.encode(),
            headers={"content-type": "text/csv", "x-filename": "cancel.csv"},
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        job_id = submitted.json()["job_id"]
        cancelled = self.client.post(f"/api/jobs/{job_id}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        completed = self._wait_for_job(job_id, timeout=25.0)
        self.assertEqual(completed["state"], "CANCELLED")
        self.assertLessEqual(completed["completed"], MAX_BATCH_ROWS)

    def test_batch_queue_is_bounded_for_multiple_jobs(self) -> None:
        manager = WebJobManager(self.app.state.web_context, max_workers=1, max_jobs=2)
        release = threading.Event()
        started = threading.Event()

        def blocked_run(job) -> None:
            started.set()
            release.wait(timeout=5.0)
            JobRepository(self.db_path).update_job_state(
                job.job_id,
                status="SUCCESS",
                details={"web_job": True, "summary": {"total": 1, "completed": 1}},
            )
            with manager._lock:
                manager._jobs.pop(job.job_id, None)

        manager._run = blocked_run  # type: ignore[method-assign]
        futures = []
        try:
            first = manager.submit(
                model_id="test-model",
                parsed=SimpleNamespace(total=1),
                input_source="first.csv",
            )
            self.assertTrue(started.wait(timeout=2.0))
            second = manager.submit(
                model_id="test-model",
                parsed=SimpleNamespace(total=1),
                input_source="second.csv",
            )
            with self.assertRaises(JobCapacityError):
                manager.submit(
                    model_id="test-model",
                    parsed=SimpleNamespace(total=1),
                    input_source="third.csv",
                )
            futures = [
                manager._jobs[first["job_id"]].future,
                manager._jobs[second["job_id"]].future,
            ]
            release.set()
            for future in futures:
                self.assertIsNotNone(future)
                future.result(timeout=5.0)
        finally:
            release.set()
            manager.shutdown()

    def test_oversized_body_and_missing_resources_are_safe(self) -> None:
        oversized = self.client.post(
            "/api/predict",
            content=b"{" + b"x" * (64 * 1024) + b"}",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(oversized.status_code, 413)
        missing = self.client.get("/api/results/00000000000000000000000000000000")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
