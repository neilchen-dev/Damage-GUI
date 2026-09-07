"""M3.1 消融实验框架测试：套件执行、错误隔离、确定性与报告落盘。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.experiments.runner import (
    ExperimentSpec,
    design_quadrant_specs,
    pod_sweep_specs,
    rbf_param_specs,
    run_suite,
    save_report,
    validation_specs,
)
from synthetic_data import make_service, make_synthetic_dataset


class ExperimentFrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp, cls.data_dir = make_synthetic_dataset()
        cls.service = make_service(cls.data_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_design_quadrant_suite_runs_all_four_configs(self) -> None:
        specs = design_quadrant_specs()
        self.assertEqual(len(specs), 4)
        results = run_suite(self.service, "F", specs, suite="design")
        self.assertEqual([r.status for r in results], ["ok"] * 4)
        row = results[0].to_dict()
        # 双口径数值指标 + 空间指标 + 追溯信息一并落列
        for key in (
            "mean_relative_error", "p95_hybrid_error", "r2", "mae",
            "raw_mean_relative_error", "raw_p95_hybrid_error",
            "centroid_error_m", "iou", "dice",
            "peak_position_error_m", "peak_intensity_error",
            "seed", "timestamp",
        ):
            self.assertIn(key, row)
        self.assertTrue(row["training_data_hash"].startswith("sha256:"))
        self.assertIsNotNone(row["train_time_seconds"])
        # 对齐开/关两个象限都被覆盖
        aligns = {(r.model_type, r.align_patterns) for r in results}
        self.assertEqual(
            aligns,
            {("rbf", False), ("rbf", True), ("pod_rbf", False), ("pod_rbf", True)},
        )

    def test_pod_sweep_records_monotonic_explained_variance(self) -> None:
        results = run_suite(self.service, "F", pod_sweep_specs(ks=(2, 4)), suite="pod")
        self.assertEqual([r.status for r in results], ["ok", "ok"])
        ev_small, ev_large = results[0].explained_variance, results[1].explained_variance
        self.assertIsNotNone(ev_small)
        self.assertIsNotNone(ev_large)
        # 累计解释方差随 K 单调不减（PCA 性质）
        self.assertGreaterEqual(ev_large, ev_small)
        self.assertGreater(ev_small, 0.0)
        self.assertEqual(results[0].n_components_used, 2)
        self.assertEqual(results[1].pod_n_components, 4)

    def test_validation_suite_isolates_unsupported_split(self) -> None:
        # 合成数据 v<=200、deg<=20，不满足角落区定义 → corner 记录为 error，
        # 同套件的 random 不受影响
        specs = [s for s in validation_specs()
                 if s.validation_mode in ("random", "corner")]
        results = run_suite(self.service, "F", specs, suite="validation")
        by_mode = {r.validation_mode: r for r in results}
        self.assertEqual(by_mode["random"].status, "ok")
        self.assertEqual(by_mode["corner"].status, "error")
        self.assertIn("角落", by_mode["corner"].error)

    def test_unknown_config_key_recorded_as_error(self) -> None:
        spec = ExperimentSpec(
            name="bad_override", config_overrides={"no_such_field": 1}
        )
        results = run_suite(self.service, "F", [spec], suite="design")
        self.assertEqual(results[0].status, "error")
        self.assertIn("TypeError", results[0].error)

    def test_rbf_param_spec_with_smoothing_and_epsilon(self) -> None:
        specs = [s for s in rbf_param_specs(
            kernels=("multiquadric",), smoothings=(1e-3,), epsilons=(0.5,),
        )]
        results = run_suite(self.service, "F", specs, suite="rbf")
        self.assertEqual(results[0].status, "ok")
        self.assertEqual(results[0].rbf_kernel, "multiquadric")
        self.assertEqual(results[0].rbf_epsilon, 0.5)
        self.assertLess(results[0].metrics["mean_relative_error"], 1.0)

    def test_results_are_deterministic_with_fixed_seed(self) -> None:
        spec = design_quadrant_specs()[1]  # rbf + 对齐开
        first = run_suite(self.service, "F", [spec], suite="design")[0]
        second = run_suite(self.service, "F", [spec], suite="design")[0]
        self.assertEqual(first.status, "ok")
        self.assertEqual(
            first.metrics["mean_relative_error"],
            second.metrics["mean_relative_error"],
        )
        self.assertEqual(first.metrics["dice"], second.metrics["dice"])

    def test_save_report_writes_csv_json_md(self) -> None:
        results = run_suite(
            self.service, "F", pod_sweep_specs(ks=(3,)), suite="pod"
        )
        with tempfile.TemporaryDirectory() as out_dir:
            paths = save_report(
                results, out_dir, "ablation_F_pod",
                level="F", data_dir=self.data_dir,
            )
            for path in paths.values():
                self.assertTrue(path.is_file())
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["n_results"], 1)
            self.assertEqual(payload["level"], "F")
            self.assertTrue(
                payload["training_data_hash"].startswith("sha256:")
            )
            frame = pd.read_csv(paths["csv"], encoding="utf-8-sig")
            self.assertIn("experiment", frame.columns)
            self.assertEqual(frame.iloc[0]["experiment"], "pod_K=3")
            md = paths["md"].read_text(encoding="utf-8")
            self.assertIn("pod_K=3", md)
            self.assertIn("实验报告", md)


if __name__ == "__main__":
    unittest.main()
