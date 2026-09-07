"""M3.8 轻量 Drift 报告的回归测试（合成数据）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from damage_gui.config import CONFIG  # noqa: E402
from damage_gui.data.loader import DamageDataManager  # noqa: E402
from damage_gui.errors import DataValidationError  # noqa: E402
from damage_gui.experiments.drift import (  # noqa: E402
    drift_report,
    load_query_conditions,
    save_drift_report,
    verdict_line,
)
from synthetic_data import make_synthetic_dataset  # noqa: E402


class DriftBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp, data_dir = make_synthetic_dataset()
        records = DamageDataManager(data_dir).get_level_records("F")
        cls.train = np.array(
            [record.condition.as_array() for record in records], dtype=np.float64
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class DriftReportTests(DriftBase):
    def test_self_comparison_detects_no_drift(self):
        report = drift_report(self.train, self.train, CONFIG)
        self.assertFalse(report["drift_detected"])
        for item in report["dimensions"].values():
            self.assertEqual(item["ks_statistic"], 0.0)
            self.assertFalse(item["drift"])
            self.assertEqual(item["out_of_range"], 0)
        self.assertEqual(report["nearest_distance"]["mean"], 0.0)
        self.assertEqual(report["nearest_distance"]["extrapolation_fraction"], 0.0)
        self.assertIn("未检测到显著漂移", verdict_line(report))

    def test_shifted_queries_are_flagged(self):
        queries = np.tile([500.0, 500.0, 80.0], (10, 1))
        report = drift_report(self.train, queries, CONFIG)
        self.assertTrue(report["drift_detected"])
        for name in ("h", "v"):
            item = report["dimensions"][name]
            self.assertTrue(item["drift"])
            self.assertEqual(item["ks_statistic"], 1.0)
            self.assertEqual(item["out_of_range"], 10)
        self.assertEqual(
            report["nearest_distance"]["extrapolation_fraction"], 1.0
        )
        self.assertIn("检测到漂移", verdict_line(report))

    def test_in_range_queries_pass(self):
        # 训练网格内的插值工况：范围覆盖完整
        queries = np.tile([2.0, 150.0, 15.0], (6, 1))
        report = drift_report(self.train, queries, CONFIG)
        for item in report["dimensions"].values():
            self.assertEqual(item["out_of_range"], 0)
        # ood_medium_max 按真实数据密度整定，对稀疏合成网格不直接适用；
        # 这里直接验证外推比例与距离阈值的一致性
        nn = report["nearest_distance"]
        self.assertEqual(
            nn["extrapolation_fraction"],
            float(nn["mean"] >= nn["extrapolation_threshold"]),
        )

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(DataValidationError):
            drift_report(self.train, np.zeros((0, 3)), CONFIG)
        with self.assertRaises(DataValidationError):
            drift_report(self.train[:1], self.train, CONFIG)
        with self.assertRaises(DataValidationError):
            drift_report(self.train, np.zeros((4, 2)), CONFIG)


class QueryCsvTests(unittest.TestCase):
    def test_roundtrip_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queries.csv"
            path.write_text("h,v,deg\n1.0,150.0,15.0\n2.5,220.0,30.0\n",
                            encoding="utf-8")
            values = load_query_conditions(path)
            np.testing.assert_array_equal(
                values, [[1.0, 150.0, 15.0], [2.5, 220.0, 30.0]]
            )

            missing = Path(tmp) / "missing.csv"
            missing.write_text("h,v\n1.0,2.0\n", encoding="utf-8")
            with self.assertRaises(DataValidationError):
                load_query_conditions(missing)

            non_numeric = Path(tmp) / "bad.csv"
            non_numeric.write_text("h,v,deg\nabc,2.0,3.0\n", encoding="utf-8")
            with self.assertRaises(DataValidationError):
                load_query_conditions(non_numeric)


class SaveDriftReportTests(DriftBase):
    def test_json_and_md_artifacts(self):
        report = drift_report(self.train, self.train, CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            paths = save_drift_report(report, tmp, "drift_F", level="F")
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["level"], "F")
            self.assertEqual(payload["n_queries"], len(self.train))
            self.assertIn("dimensions", payload)
            md = paths["md"].read_text(encoding="utf-8")
            self.assertIn("输入分布漂移报告", md)
            self.assertIn("逐维 KS 检验", md)
            self.assertIn("局限说明", md)


if __name__ == "__main__":
    unittest.main()
