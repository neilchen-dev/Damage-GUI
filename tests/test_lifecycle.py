"""M3.6 模型生命周期的回归测试（真实训练产物 + 状态机）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from damage_gui.errors import LifecycleError  # noqa: E402
from damage_gui.model.lifecycle import ModelRegistry  # noqa: E402
from damage_gui.model.registry import save_model  # noqa: E402
from synthetic_data import make_service, make_synthetic_dataset  # noqa: E402


class LifecycleBase(unittest.TestCase):
    """共享两个真实训练产物（不同 model_id），避免每个用例重复训练。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._data_tmp, data_dir = make_synthetic_dataset()
        service = make_service(data_dir)
        cls.bundle_a = service.train_bundle("F")
        cls.bundle_b = service.train_bundle("F")
        cls._work_tmp = tempfile.TemporaryDirectory()
        cls.work_dir = Path(cls._work_tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._work_tmp.cleanup()
        cls._data_tmp.cleanup()

    def setUp(self) -> None:
        self._db_tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._db_tmp.name) / "lifecycle.sqlite3"
        self.model_a = self.work_dir / f"model_a_{id(self)}.joblib"
        self.model_b = self.work_dir / f"model_b_{id(self)}.joblib"
        save_model(self.bundle_a, self.model_a)
        save_model(self.bundle_b, self.model_b)

    def tearDown(self) -> None:
        self._db_tmp.cleanup()


class RegisterTests(LifecycleBase):
    def test_register_reads_sidecar_and_starts_draft(self) -> None:
        with ModelRegistry(self.db_path) as registry:
            row_id = registry.register(self.model_a, notes="首次训练")
            record = registry.get(row_id)
            self.assertEqual(record["status"], "DRAFT")
            self.assertEqual(record["level"], "F")
            self.assertEqual(record["model_id"], self.bundle_a.metadata.model_id)
            self.assertIsNone(registry.active("F"))

            frame = registry.list_models()
            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.iloc[0]["notes"], "首次训练")

    def test_register_without_sidecar_rejected(self) -> None:
        orphan = self.work_dir / "orphan.joblib"
        orphan.write_bytes(b"not a real model")
        with ModelRegistry(self.db_path) as registry:
            with self.assertRaises(LifecycleError) as ctx:
                registry.register(orphan)
        self.assertIn("元数据", str(ctx.exception))

    def test_duplicate_register_rejected(self) -> None:
        with ModelRegistry(self.db_path) as registry:
            registry.register(self.model_a)
            with self.assertRaises(LifecycleError) as ctx:
                registry.register(self.model_a)
        self.assertIn("已登记", str(ctx.exception))


class TransitionTests(LifecycleBase):
    def test_full_flow_and_single_active_per_family(self) -> None:
        with ModelRegistry(self.db_path) as registry:
            id_a = registry.register(self.model_a)
            registry.transition(id_a, "VALIDATED")
            active_row = registry.transition(id_a, "ACTIVE")
            self.assertEqual(registry.active("F")["id"], id_a)
            self.assertEqual(active_row["replaced"], [])

            id_b = registry.register(self.model_b)
            registry.transition(id_b, "VALIDATED")
            updated = registry.transition(id_b, "ACTIVE")
            self.assertEqual(updated["replaced"], [id_a])
            self.assertEqual(registry.active("F")["id"], id_b)

            # 同等级只剩一个 ACTIVE，原 ACTIVE 已归档且留有痕迹
            actives = registry.list_models(status="ACTIVE")
            self.assertEqual(list(actives["id"]), [id_b])
            self.assertIn("替换下线", registry.get(id_a)["notes"])

    def test_illegal_transitions_rejected(self) -> None:
        with ModelRegistry(self.db_path) as registry:
            row_id = registry.register(self.model_a)
            with self.assertRaises(LifecycleError) as ctx:
                registry.transition(row_id, "ACTIVE")  # DRAFT 不能跳级
            self.assertIn("非法状态转移", str(ctx.exception))

            registry.transition(row_id, "VALIDATED")
            registry.transition(row_id, "ACTIVE")
            with self.assertRaises(LifecycleError):
                registry.transition(row_id, "VALIDATED")  # ACTIVE 不能回退
            registry.transition(row_id, "ARCHIVED")
            with self.assertRaises(LifecycleError):
                registry.transition(row_id, "DRAFT")  # 终态
            with self.assertRaises(LifecycleError):
                registry.transition(row_id, "ARCHIVED")  # 同状态重复

    def test_missing_record_and_unknown_state(self) -> None:
        with ModelRegistry(self.db_path) as registry:
            with self.assertRaises(LifecycleError):
                registry.get(999)
            row_id = registry.register(self.model_a)
            with self.assertRaises(LifecycleError):
                registry.transition(row_id, "SHIPPED")

    def test_list_filters_by_level_and_status(self) -> None:
        with ModelRegistry(self.db_path) as registry:
            id_a = registry.register(self.model_a)
            registry.register(self.model_b)
            registry.transition(id_a, "VALIDATED")
            self.assertEqual(len(registry.list_models(level="F")), 2)
            self.assertEqual(len(registry.list_models(level="M")), 0)
            validated = registry.list_models(status="VALIDATED")
            self.assertEqual(list(validated["id"]), [id_a])
            with self.assertRaises(LifecycleError):
                registry.list_models(status="SHIPPED")


if __name__ == "__main__":
    unittest.main()
