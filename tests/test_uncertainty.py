"""M3.4 不确定度估计与校准验证的回归测试（合成数据）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from damage_gui.data.loader import Condition  # noqa: E402
from damage_gui.experiments.uncertainty import (  # noqa: E402
    UncertaintyEstimator,
    calibration_bins,
    run_uncertainty_study,
    save_uncertainty_report,
)
from synthetic_data import make_service, make_synthetic_dataset  # noqa: E402


class EstimatorTests(unittest.TestCase):
    def test_distance_and_residual_knn(self) -> None:
        conditions = np.array(
            [[float(i), 100.0, 10.0] for i in range(5)]
        )
        residuals = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        estimator = UncertaintyEstimator(conditions, residuals, k=2)

        # 查询就在训练点 0：最近两个残差为 0.1 与 0.2
        self.assertAlmostEqual(
            estimator.residual_knn(Condition(0.0, 100.0, 10.0)), 0.15
        )
        near = estimator.knn_distance(Condition(0.0, 100.0, 10.0))
        far = estimator.knn_distance(Condition(50.0, 999.0, 89.0))
        self.assertGreater(far, near)


class CalibrationBinsTests(unittest.TestCase):
    def test_perfect_estimator_binning(self) -> None:
        estimates = np.linspace(0.0, 1.0, 40)
        errors = estimates.copy()
        bins = calibration_bins(estimates, errors, n_bins=4)
        self.assertEqual(len(bins), 4)
        np.testing.assert_allclose(
            bins["mean_estimate"], bins["mean_error"], atol=1e-12
        )
        self.assertTrue((bins["mean_error"].diff().dropna() >= 0).all())

    def test_degenerate_estimates_collapse_to_single_bin(self) -> None:
        bins = calibration_bins(np.zeros(10), np.linspace(0, 1, 10), n_bins=4)
        self.assertEqual(len(bins), 1)
        self.assertEqual(int(bins.iloc[0]["n"]), 10)


class UncertaintyStudyTests(unittest.TestCase):
    def test_loo_study_and_report_on_synthetic_data(self) -> None:
        tmp, _data_dir = make_synthetic_dataset()
        try:
            service = make_service(Path(tmp.name))
            study = run_uncertainty_study(
                service, "F", model_type="rbf", k=3, n_bins=3
            )
        finally:
            tmp.cleanup()

        summary = study["summary"]
        self.assertEqual(summary["n_samples"], 12)
        self.assertGreater(summary["error_mean"], 0.0)
        for key in ("spearman_distance", "spearman_residual_knn"):
            value = summary[key]
            self.assertTrue(
                np.isnan(value) or -1.0 <= value <= 1.0, f"{key} 应为相关系数或 NaN"
            )
        # 合成数据仅 3 个 h 层，LOO k=3 的第 3 近距离逐样本恒定，
        # 距离估计器区分不出排序（NaN 是如实结果）；残差估计器仍应可算
        self.assertTrue(np.isfinite(summary["spearman_residual_knn"]))
        samples = study["samples"]
        self.assertEqual(len(samples), 12)
        for key in ("error", "est_distance", "est_residual_knn"):
            self.assertTrue(np.isfinite(samples[key]).all())
        for bins in study["bins"].values():
            self.assertIsInstance(bins, pd.DataFrame)
            self.assertFalse(bins.empty)

        with tempfile.TemporaryDirectory() as out:
            paths = save_uncertainty_report(study, out, "uncertainty_F_rbf")
            for path in paths.values():
                self.assertTrue(path.is_file(), path)
            self.assertTrue(paths["png"].stat().st_size > 0)
            md = paths["md"].read_text(encoding="utf-8")
            self.assertIn("Spearman", md)
            self.assertIn("校准分箱", md)


if __name__ == "__main__":
    unittest.main()
