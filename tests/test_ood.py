"""OOD / 预测可信度检测测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.data.loader import Condition
from damage_gui.model.ood import (
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    OODDetector,
)


class OODDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.detector = OODDetector(high_max=0.15, medium_max=0.3)
        cls.detector.fit(
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
        )

    def test_training_point_is_high_confidence(self) -> None:
        report = self.detector.report(Condition(0.0, 0.0, 0.0))
        self.assertAlmostEqual(report.distance, 0.0, places=9)
        self.assertEqual(report.level, LEVEL_HIGH)
        self.assertTrue(report.is_reliable)

    def test_interior_point_is_medium_confidence(self) -> None:
        # 最近训练工况距离 = 0.25 → Medium
        report = self.detector.report(Condition(0.25, 0.0, 0.0))
        self.assertAlmostEqual(report.distance, 0.25, places=9)
        self.assertEqual(report.level, LEVEL_MEDIUM)
        self.assertTrue(report.is_reliable)

    def test_far_point_is_low_confidence(self) -> None:
        report = self.detector.report(Condition(10.0, 10.0, 10.0))
        self.assertEqual(report.level, LEVEL_LOW)
        self.assertFalse(report.is_reliable)
        self.assertGreater(report.distance, 0.3)

    def test_nearest_condition_reported(self) -> None:
        report = self.detector.report(Condition(0.95, 0.0, 0.0))
        self.assertAlmostEqual(report.nearest_condition["h"], 1.0, places=9)

    def test_unfitted_detector_raises(self) -> None:
        detector = OODDetector()
        with self.assertRaises(RuntimeError):
            detector.report(Condition(0.0, 0.0, 0.0))

    def test_invalid_thresholds_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OODDetector(high_max=0.5, medium_max=0.2)
        with self.assertRaises(ValueError):
            OODDetector(local_neighbors=-1)
        with self.assertRaises(ValueError):
            OODDetector(max_1d_gap_ratio=1.0)

    def test_describe_mentions_warning_for_low_confidence(self) -> None:
        report = self.detector.report(Condition(10.0, 10.0, 10.0))
        self.assertIn("外推", self.detector.describe(report))


class HullDetectionTests(unittest.TestCase):
    """全局与局部凸包检测：处理近邻距离无法识别的几何外推。

    训练分布（(h, v) 平面，deg 恒为 0 → 共面，走降维子空间）：
        A=(0,0), B=(1,0), C=(0.5, 0.55) 三角形。
    凸包边 A→C 在直线 v = 1.1·h 上方一侧为外部（B 在下方，三角形内部
    在 A→C 连线下方）。
    查询点 (0.45, 0.52)：到最近训练点 C 的距离 ≈ 0.074 < 0.15
    （距离级 High），但 v=0.52 > 1.1·h=0.495，位于凸包外 ——
    正是"近但凸包外"的盲区场景。
    """

    TRAINING = np.array(
        [
            # (h, v, deg)
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 0.55, 0.0],
        ],
        dtype=np.float64,
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.detector = OODDetector()
        cls.detector.fit(cls.TRAINING)

    def test_hull_is_built_for_coplanar_set(self) -> None:
        # deg 全为 0（共面）时应降维到 (h, v) 子空间，凸包仍可用
        self.assertTrue(self.detector.hull_available)

    def test_point_inside_hull_keeps_high_confidence(self) -> None:
        # 归一化后三角形 A(0,0), B(1,0), C(0.5,1)；(0.95, 0.0275)→(0.95, 0.05)
        # 位于三角形内部（B→C 边内侧）且距 B ≈ 0.07
        report = self.detector.report(Condition(0.95, 0.0275, 0.0))
        self.assertTrue(report.in_hull)
        self.assertEqual(report.level, "high")

    def test_point_near_but_outside_hull_is_downgraded(self) -> None:
        """三角形外侧：最近距离 ≈0.07（High 区间），凸包外 → Medium。"""
        report = self.detector.report(Condition(0.45, 0.52, 0.0))
        self.assertLess(report.distance, 0.15, "前置条件：最近距离应在 High 区间")
        self.assertFalse(report.in_hull)
        self.assertNotEqual(report.level, "high")
        self.assertEqual(report.level, "medium")

    def test_arbitrary_diagonal_line_is_reduced_to_one_dimension(self) -> None:
        # 三个原始维度都变化，但训练点只位于斜向直线上；SVD 应识别为 1D。
        detector = OODDetector()
        detector.fit(
            np.array([[i, i, i] for i in range(6)], dtype=np.float64)
        )
        self.assertTrue(detector.hull_available)
        self.assertEqual(detector.intrinsic_dimension, 1)
        on_line = detector.report(Condition(2.5, 2.5, 2.5))
        self.assertTrue(on_line.in_hull)
        off_line = detector.report(Condition(2.5, 2.5, 2.6))
        self.assertFalse(off_line.in_hull)

    def test_single_effective_dimension_uses_interval_hull(self) -> None:
        # 只有一个维度变化 → 一维区间判定
        detector = OODDetector()
        detector.fit(
            np.array([[0.0, 5.0, 0.0], [1.0, 5.0, 0.0], [0.5, 5.0, 0.0]], dtype=np.float64)
        )
        self.assertTrue(detector.hull_available)
        inside = detector.report(Condition(0.5, 5.0, 0.0))
        self.assertTrue(inside.in_hull)
        outside = detector.report(Condition(1.5, 5.0, 0.0))
        self.assertFalse(outside.in_hull)

    def test_describe_mentions_hull_for_outside_point(self) -> None:
        report = self.detector.report(Condition(0.45, 0.52, 0.0))
        text = self.detector.describe(report)
        self.assertIn("凸包", text)

    def test_hull_can_be_disabled(self) -> None:
        detector = OODDetector(use_hull=False)
        detector.fit(self.TRAINING)
        self.assertFalse(detector.hull_available)
        # 纯距离模式下同一查询点仍是 high（旧行为，向后兼容）
        report = detector.report(Condition(0.45, 0.52, 0.0))
        self.assertIsNone(report.in_hull)
        self.assertEqual(report.level, "high")

    def test_arbitrary_plane_projection_and_off_plane_rejection(self) -> None:
        training = np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0],
                [1.0, 1.0, 2.0],
            ]
        )
        detector = OODDetector().fit(training)
        self.assertEqual(detector.intrinsic_dimension, 2)
        self.assertTrue(detector.report(Condition(0.25, 0.25, 0.5)).in_hull)
        self.assertFalse(detector.report(Condition(0.25, 0.25, 0.7)).in_hull)

    def test_local_hull_detects_dense_l_shape_gap(self) -> None:
        values = np.linspace(0.0, 1.0, 21)
        training = np.vstack(
            [
                np.column_stack([values, np.zeros_like(values), np.zeros_like(values)]),
                np.column_stack([np.zeros_like(values), values, np.zeros_like(values)]),
            ]
        )
        detector = OODDetector().fit(training)
        report = detector.report(Condition(0.1, 0.1, 0.0))
        self.assertLess(report.distance, detector.high_max)
        self.assertTrue(report.in_hull, "该点位于全局凸包内")
        self.assertFalse(report.local_support, "局部邻域不应跨越 L 形空洞")
        self.assertEqual(report.level, LEVEL_MEDIUM)
        self.assertTrue(report.is_extrapolation)
        self.assertIn("数据空洞", detector.describe(report))

    def test_automatic_neighbors_do_not_flag_regular_3d_grid_hole(self) -> None:
        """规则网格单点留出仍有四周训练点支撑，不应误报成凹形空洞。"""
        values = np.linspace(0.0, 1.0, 5)
        training = np.array(
            [
                (x, y, z)
                for x in values
                for y in values
                for z in values
                if (x, y, z) != (0.5, 0.5, 0.5)
            ]
        )
        report = OODDetector().fit(training).report(Condition(0.5, 0.5, 0.5))
        self.assertTrue(report.in_hull)
        self.assertTrue(report.local_support)

    def test_local_support_can_be_disabled(self) -> None:
        values = np.linspace(0.0, 1.0, 21)
        training = np.vstack(
            [
                np.column_stack([values, np.zeros_like(values), np.zeros_like(values)]),
                np.column_stack([np.zeros_like(values), values, np.zeros_like(values)]),
            ]
        )
        detector = OODDetector(use_local_support=False).fit(training)
        report = detector.report(Condition(0.1, 0.1, 0.0))
        self.assertIsNone(report.local_support)
        self.assertEqual(report.level, LEVEL_HIGH)


if __name__ == "__main__":
    unittest.main()
