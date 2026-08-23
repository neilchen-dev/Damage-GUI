"""SQLite 追溯数据库测试：schema、仓储 CRUD 与故障降级（显式记录不静默）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.model.metadata import ModelMetadata
from damage_gui.storage.db import init_database, resolve_db_path
from damage_gui.storage.repositories import (
    JobRepository,
    ModelRepository,
    PredictionResultRepository,
)


def sample_metadata(**overrides) -> ModelMetadata:
    values = dict(
        model_id="test-model-id-0001",
        created_at="2026-08-23T00:00:00+00:00",
        app_version="2.1.0",
        schema_version=1,
        model_format_version=1,
        model_type="rbf",
        damage_level="F",
        training_samples=96,
        training_data_hash="sha256:abc123",
        code_commit=None,
        parameters={"validation_mode": "random"},
        validation={"method": "random", "mean_relative_error": 0.08},
    )
    values.update(overrides)
    return ModelMetadata(**values)


class DatabaseTests(unittest.TestCase):
    def test_init_creates_database_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "trace.db"
            self.assertTrue(init_database(db_path))
            self.assertTrue(db_path.is_file())
            self.assertTrue(init_database(db_path))  # 幂等

    def test_init_failure_is_logged_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # 把目录当数据库文件使用 → sqlite 报错
            bad_path = Path(tmp) / "as_dir.db"
            bad_path.mkdir()
            with self.assertLogs("damage_gui.storage", level="ERROR"):
                self.assertFalse(init_database(bad_path))

    def test_resolve_db_path_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"DAMAGE_GUI_DB": "X:/custom/db.sqlite"}):
            self.assertEqual(resolve_db_path(), Path("X:/custom/db.sqlite"))
        self.assertEqual(resolve_db_path("explicit.db"), Path("explicit.db"))


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "trace.db"
        self.assertTrue(init_database(self.db_path))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_model_upsert_and_list(self) -> None:
        repo = ModelRepository(self.db_path)
        self.assertTrue(repo.upsert_model(sample_metadata(), artifact_path="m.joblib"))
        models = repo.list_models()
        assert models is not None
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "test-model-id-0001")
        self.assertEqual(models[0]["damage_level"], "F")
        # 同 model_id 再写一次 → 替换不追加
        self.assertTrue(
            repo.upsert_model(sample_metadata(training_samples=120))
        )
        models = repo.list_models()
        assert models is not None
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["training_samples"], 120)

    def test_job_insert_get_and_recent(self) -> None:
        repo = JobRepository(self.db_path)
        job_id = repo.insert_job(
            kind="training", status="SUCCESS",
            input_source="data", duration_ms=1234,
            details={"mean_relative_error": 0.08},
        )
        self.assertIsNotNone(job_id)
        job = repo.get_job(job_id)  # type: ignore[arg-type]
        self.assertEqual(job["kind"], "training")
        self.assertEqual(job["status"], "SUCCESS")
        self.assertEqual(job["duration_ms"], 1234)
        self.assertIsNotNone(job["started_at"])
        self.assertIsNotNone(job["finished_at"])
        recent = repo.recent_jobs(limit=5)
        assert recent is not None
        self.assertEqual(len(recent), 1)

    def test_record_training_run_composite(self) -> None:
        repo = JobRepository(self.db_path)
        metadata = sample_metadata()
        job_id = repo.record_training_run(
            metadata, input_source="data/F", duration_ms=999,
            details={"train_time_seconds": 1.0},
        )
        self.assertIsNotNone(job_id)
        models = ModelRepository(self.db_path).list_models()
        assert models is not None
        self.assertEqual(len(models), 1)
        job = repo.get_job(job_id)  # type: ignore[arg-type]
        self.assertEqual(job["model_id"], metadata.model_id)

    def test_batch_results_recorded(self) -> None:
        jobs = JobRepository(self.db_path)
        job_id = jobs.insert_job(kind="batch_prediction", status="SUCCESS")
        assert job_id is not None
        rows = [
            {
                "job_id": "0001", "level": "F", "h": 1.0, "v": 300.0, "deg": 30.0,
                "status": "SUCCESS", "ood_level": "high", "ood_distance": 0.02,
                "peak_intensity": 0.98, "damage_area_ratio": 0.05,
                "mean_relative_error": 0.07, "p95_hybrid_error": 0.15,
                "duration_ms": 12, "error_message": None,
            },
            {
                "job_id": "0002", "level": "F", "h": 2.0, "v": 350.0, "deg": 40.0,
                "status": "FAILED", "error_message": "输入校验失败: h 超出范围",
            },
        ]
        repo = PredictionResultRepository(self.db_path)
        self.assertTrue(repo.record_batch_results(job_id=job_id, rows=rows))
        with _connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM prediction_results WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            self.assertEqual(count, 2)
            failed = conn.execute(
                "SELECT error_summary FROM prediction_results "
                "WHERE status = 'FAILED'"
            ).fetchone()[0]
            self.assertIn("超出范围", failed)


class RepositoryFailureTests(unittest.TestCase):
    """SQLite 故障降级：计算可继续，但必须显式记录 ERROR 日志（不静默）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # 用一个已存在的目录冒充数据库文件 → 所有写入操作必然失败
        bad_path = Path(self._tmp.name) / "bad.db"
        bad_path.mkdir()
        self.bad_path = bad_path

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_model_repo_failure_returns_false_with_error_log(self) -> None:
        repo = ModelRepository(self.bad_path)
        with self.assertLogs("damage_gui.storage", level="ERROR") as logs:
            self.assertFalse(repo.upsert_model(sample_metadata()))
        self.assertTrue(any("models" in message for message in logs.output))

    def test_job_repo_failure_returns_none_with_error_log(self) -> None:
        repo = JobRepository(self.bad_path)
        with self.assertLogs("damage_gui.storage", level="ERROR"):
            job_id = repo.insert_job(kind="training", status="SUCCESS")
        self.assertIsNone(job_id)
        with self.assertLogs("damage_gui.storage", level="ERROR"):
            self.assertIsNone(repo.get_job("whatever"))

    def test_training_run_composite_failure_reports(self) -> None:
        repo = JobRepository(self.bad_path)
        with self.assertLogs("damage_gui.storage", level="ERROR"):
            job_id = repo.record_training_run(
                sample_metadata(), input_source="data", duration_ms=1
            )
        self.assertIsNone(job_id)

    def test_batch_results_failure_returns_false_with_error_log(self) -> None:
        repo = PredictionResultRepository(self.bad_path)
        with self.assertLogs("damage_gui.storage", level="ERROR"):
            self.assertFalse(
                repo.record_batch_results(job_id="j1", rows=[{"job_id": "1"}])
            )


@contextmanager
def _connect(db_path: Path):
    """测试用连接：退出时真正关闭（Windows 下未关闭会锁住文件）。"""
    from damage_gui.storage.db import connect

    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
