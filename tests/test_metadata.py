"""模型元数据与注册表测试：三版本号、数据指纹、sidecar 双写与加载校验。"""
from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
import unittest
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui import __version__
from damage_gui.errors import ModelLoadError
from damage_gui.model.metadata import (
    METADATA_SCHEMA_VERSION,
    MODEL_FORMAT_VERSION,
    ModelMetadata,
    sidecar_path,
    training_data_hash,
)
from damage_gui.model.registry import load_model, save_model
from synthetic_data import make_service, make_synthetic_dataset


class MetadataBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp, cls.data_dir = make_synthetic_dataset()
        cls.service = make_service(cls.data_dir)
        cls.bundle = cls.service.train_bundle(
            "F", validation_mode="random", model_type="rbf"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_bundle_carries_metadata_with_version_trio(self) -> None:
        metadata = self.bundle.metadata
        self.assertIsNotNone(metadata)
        assert metadata is not None  # 供类型检查器收窄
        # 三个版本号职责不同且分别记录
        self.assertEqual(metadata.app_version, __version__)
        self.assertEqual(metadata.schema_version, METADATA_SCHEMA_VERSION)
        self.assertEqual(metadata.model_format_version, MODEL_FORMAT_VERSION)
        self.assertEqual(metadata.model_type, "rbf")
        self.assertEqual(metadata.damage_level, "F")
        self.assertEqual(metadata.training_samples, len(self.bundle.train_conditions))
        self.assertTrue(metadata.training_data_hash.startswith("sha256:"))
        self.assertEqual(metadata.parameters["validation_mode"], "random")
        self.assertEqual(metadata.validation["method"], "random")
        self.assertIn("mean_relative_error", metadata.validation)
        # P0-2 双口径：主口径显式标注为 Smoothed，Raw 口径并列记录
        self.assertEqual(metadata.validation["primary_field"], "smoothed")
        self.assertIn("raw_mean_relative_error", metadata.validation)

    def test_metadata_dict_roundtrip(self) -> None:
        metadata = self.bundle.metadata
        assert metadata is not None
        restored = ModelMetadata.from_dict(json.loads(json.dumps(metadata.to_dict())))
        self.assertEqual(restored, metadata)

    def test_from_dict_rejects_future_schema(self) -> None:
        data = self.bundle.metadata.to_dict()  # type: ignore[union-attr]
        data["schema_version"] = METADATA_SCHEMA_VERSION + 1
        with self.assertRaisesRegex(ModelLoadError, "高于当前软件支持"):
            ModelMetadata.from_dict(data)

    def test_from_dict_rejects_missing_fields(self) -> None:
        data = self.bundle.metadata.to_dict()  # type: ignore[union-attr]
        del data["training_data_hash"]
        with self.assertRaisesRegex(ModelLoadError, "缺少字段"):
            ModelMetadata.from_dict(data)

    def test_summary_lines_show_dual_criteria(self) -> None:
        metadata = self.bundle.metadata
        assert metadata is not None
        lines = metadata.summary_lines()
        self.assertTrue(any("主口径: Smoothed" in line for line in lines))
        self.assertTrue(any(line.startswith("Smoothed:") for line in lines))
        self.assertTrue(any(line.startswith("Raw:") for line in lines))

    def test_summary_lines_legacy_single_criterion(self) -> None:
        # 旧版元数据无 raw_* 键 → 回退单口径摘要行，保持向后兼容
        metadata = self.bundle.metadata
        assert metadata is not None
        legacy = dataclasses.replace(
            metadata,
            validation={"method": "random", "mean_relative_error": 0.05},
        )
        lines = legacy.summary_lines()
        self.assertTrue(any("验证: random，MeanRE" in line for line in lines))
        self.assertFalse(any(line.startswith("Raw:") for line in lines))


class TrainingDataHashTests(unittest.TestCase):
    def test_hash_is_stable_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from damage_gui.data.loader import DamageDataManager

            data_dir = Path(tmp)
            # 两个工况文件，内容不同
            for name, value in (("DamageMatrix_F_h_10_v_100_deg_10", 0.5),
                                ("DamageMatrix_F_h_20_v_100_deg_10", 0.8)):
                (data_dir / name).write_text(
                    "header\n" + "\t".join([str(value)] * 8) + "\n",
                    encoding="gbk",
                )
            records = DamageDataManager(data_dir).get_level_records("F")
            first = training_data_hash(records)
            self.assertEqual(first, training_data_hash(records))  # 稳定

            # 修改一个文件的内容（文件名不变）→ 指纹必须变化
            target = data_dir / "DamageMatrix_F_h_10_v_100_deg_10"
            target.write_text("header\n" + "\t".join(["0.9"] * 8) + "\n",
                              encoding="gbk")
            self.assertNotEqual(first, training_data_hash(records))


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp, cls.data_dir = make_synthetic_dataset()
        service = make_service(cls.data_dir)
        cls.bundle = service.train_bundle(
            "F", validation_mode="random", model_type="rbf"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _save(self, tmp: str) -> Path:
        model_path = Path(tmp) / "model.joblib"
        save_model(self.bundle, model_path)
        return model_path

    def test_save_writes_joblib_and_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model_path = self._save(tmp)
            self.assertTrue(model_path.is_file())
            sidecar = sidecar_path(model_path)
            self.assertEqual(sidecar.name, "model.meta.json")
            self.assertTrue(sidecar.is_file())
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(data["model_id"], self.bundle.metadata.model_id)  # type: ignore[union-attr]

    def test_load_model_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model_path = self._save(tmp)
            loaded = load_model(model_path)
            self.assertIsNotNone(loaded.metadata)
            assert loaded.metadata is not None
            self.assertEqual(loaded.metadata.model_id,
                             self.bundle.metadata.model_id)  # type: ignore[union-attr]

    def test_load_rejects_corrupted_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "broken.joblib"
            bad.write_bytes(b"this is not a joblib file")
            with self.assertRaisesRegex(ModelLoadError, "损坏"):
                load_model(bad)

    def test_load_rejects_wrong_payload_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "wrong.joblib"
            joblib.dump({"not": "a bundle"}, wrong)
            with self.assertRaisesRegex(ModelLoadError, "不是 ModelBundle"):
                load_model(wrong)

    def test_load_rejects_missing_file(self) -> None:
        with self.assertRaisesRegex(ModelLoadError, "不存在"):
            load_model(Path("nowhere") / "missing.joblib")

    def test_load_rejects_sidecar_model_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model_path = self._save(tmp)
            sidecar = sidecar_path(model_path)
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            data["model_id"] = "tampered"
            sidecar.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ModelLoadError, "不匹配"):
                load_model(model_path)

    def test_load_legacy_model_without_metadata(self) -> None:
        # 旧版模型：joblib 主文件、无 sidecar、bundle 无 metadata 字段
        with tempfile.TemporaryDirectory() as tmp:
            legacy = dataclasses.replace(self.bundle, metadata=None)
            legacy_path = Path(tmp) / "legacy.joblib"
            joblib.dump(legacy, legacy_path)
            loaded = load_model(legacy_path)
            self.assertIsNone(getattr(loaded, "metadata", None))


if __name__ == "__main__":
    unittest.main()
