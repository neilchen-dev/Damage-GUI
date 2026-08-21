"""端到端合成数据集测试：完整走通 DamageModelService 训练管线。

用临时目录生成符合命名规范的 DamageMatrix 文件，验证：
- 随机留出训练 → 报告结构（Raw/Smoothed 双口径 + 空间指标行）
- 整层留出（leave_h_out）训练 → 聚合折外指标 + 全量重训练交付模型
- OOD 检测器随 bundle 一同产出
- 预测值域与形状
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition, DamageDataManager
from damage_gui.model.bundle import DamageModelService

SHAPE = (64, 64)


def synthetic_matrix(h: float, v: float, deg: float) -> np.ndarray:
    """幅值随工况变化的中心高斯场（带轻微位置移动以锻炼质心对齐）。"""
    rows, cols = np.meshgrid(
        np.arange(SHAPE[0], dtype=float), np.arange(SHAPE[1], dtype=float), indexing="ij"
    )
    center_row = 31.5 + (h - 2.0) * 1.0
    center_col = 31.5 + (h - 2.0) * 1.5
    dr = rows - center_row
    dc = cols - center_col
    amplitude = 0.4 + 0.1 * h + 0.0002 * v + 0.004 * deg
    return np.clip(
        amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * 3.5 * 3.5)), 0.0, 1.0
    )


def write_synthetic_dataset(directory: Path) -> None:
    for h in (1.0, 2.0, 3.0):
        for v in (100.0, 200.0):
            for deg in (10.0, 20.0):
                matrix = synthetic_matrix(h, v, deg)
                name = (
                    f"DamageMatrix_F_h_{int(h * 10)}"
                    f"_v_{int(v * 10)}_deg_{int(deg * 10)}"
                )
                lines = ["synthetic_header"]
                for row in matrix:
                    lines.append("\t".join(f"{value:.6f}" for value in row))
                (directory / name).write_text(
                    "\n".join(lines) + "\n", encoding="gbk"
                )


def make_service(directory: Path) -> DamageModelService:
    config = dataclasses.replace(CONFIG, target_shape=SHAPE, eval_smoothing_sigma=1.0)
    return DamageModelService(DamageDataManager(directory), config=config)


class EndToEndSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls._tmp.name)
        write_synthetic_dataset(cls.data_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_random_holdout_pipeline(self) -> None:
        service = make_service(self.data_dir)
        bundle = service.train_bundle("F", validation_mode="random", model_type="rbf")
        self.assertEqual(bundle.validation_mode, "random")
        self.assertEqual(bundle.model_type, "rbf")
        self.assertGreater(bundle.train_time_seconds, 0.0)
        self.assertEqual(bundle.resolved_config(), service.config)
        self.assertEqual(bundle.model.config, service.config)

        # 训练/测试划分
        self.assertEqual(
            len(bundle.train_conditions) + len(bundle.test_conditions), 12
        )
        train_keys = {
            (c["h"], c["v"], c["deg"]) for c in bundle.train_conditions
        }
        test_keys = {(c["h"], c["v"], c["deg"]) for c in bundle.test_conditions}
        self.assertFalse(train_keys & test_keys)

        # 报告结构：scope × field 双口径 + 空间指标汇总行
        report = bundle.accuracy_report
        self.assertFalse(report.empty)
        self.assertIn("field", report.columns)
        self.assertEqual(set(report["field"]), {"raw", "smoothed"})
        self.assertIn("spatial", set(report["scope"]))
        focus = report[
            (report["scope"] == "damage_gt_0.05") & (report["field"] == "smoothed")
        ]
        self.assertEqual(len(focus), 1)
        spatial_row = report[report["scope"] == "spatial"].iloc[0]
        self.assertFalse(np.isnan(spatial_row["IoU"]))

        # 条件报告含空间指标列与 Raw 口径列
        condition = bundle.condition_report.iloc[0]
        self.assertIn("Spat_IoU", bundle.condition_report.columns)
        self.assertIn("Spat_Dice", bundle.condition_report.columns)
        self.assertIn("RawP95HybridError_gt_0.05", bundle.condition_report.columns)
        self.assertFalse(np.isnan(condition["Spat_IoU"]))

        # OOD 检测器已拟合
        self.assertIsNotNone(bundle.ood_detector)
        self.assertTrue(bundle.ood_detector.is_fitted)
        report_ood = bundle.ood_detector.report(
            Condition(**bundle.train_conditions[0])
        )
        self.assertAlmostEqual(report_ood.distance, 0.0, places=6)

        # 预测：形状 + 值域 + ROI 外为 0
        prediction = service.predict_matrix(bundle, Condition(2.0, 150.0, 15.0))
        self.assertEqual(prediction.shape, SHAPE)
        self.assertGreaterEqual(float(prediction.min()), 0.0)
        self.assertLessEqual(float(prediction.max()), 1.0)

    def test_leave_h_out_pipeline(self) -> None:
        service = make_service(self.data_dir)
        bundle = service.train_bundle(
            "F", validation_mode="leave_h_out", model_type="rbf"
        )
        # 折外指标覆盖全部工况，交付模型在全部工况上重训练
        self.assertEqual(len(bundle.test_conditions), 12)
        self.assertEqual(len(bundle.train_conditions), 12)
        self.assertFalse(bundle.accuracy_report.empty)

    def test_pod_rbf_pipeline(self) -> None:
        service = make_service(self.data_dir)
        bundle = service.train_bundle(
            "F", validation_mode="random", model_type="pod_rbf",
            pod_n_components=5,
        )
        self.assertEqual(bundle.model_type, "pod_rbf")
        self.assertGreater(bundle.model.explained_variance, 0.9)
        prediction = service.predict_matrix(bundle, Condition(2.0, 150.0, 15.0))
        self.assertEqual(prediction.shape, SHAPE)
        self.assertLessEqual(float(prediction.max()), 1.0)

    def test_cancel_check_aborts_training(self) -> None:
        from damage_gui.model.bundle import TrainingCancelled

        service = make_service(self.data_dir)
        with self.assertRaises(TrainingCancelled):
            service.train_bundle("F", cancel_check=lambda: True)


if __name__ == "__main__":
    unittest.main()
