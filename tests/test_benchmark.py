"""M3.3 性能基准的轻量回归测试（合成数据，小批量）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd

from damage_gui.experiments.benchmark import (  # noqa: E402
    latency_stats,
    run_model_benchmark,
    save_benchmark_report,
)
from synthetic_data import make_service, make_synthetic_dataset  # noqa: E402


class LatencyStatsTests(unittest.TestCase):
    def test_stats_are_exact_for_known_input(self) -> None:
        stats = latency_stats([0.1, 0.2, 0.3])
        self.assertAlmostEqual(stats["mean_ms"], 200.0)
        self.assertAlmostEqual(stats["median_ms"], 200.0)
        self.assertAlmostEqual(stats["p95_ms"], 290.0)
        self.assertAlmostEqual(stats["throughput_per_s"], 3.0 / 0.6)


class ModelBenchmarkTests(unittest.TestCase):
    def test_full_benchmark_rows_and_report(self) -> None:
        tmp, _data_dir = make_synthetic_dataset()
        try:
            service = make_service(Path(tmp.name))
            rows = run_model_benchmark(
                service, "F", "rbf", batch_sizes=(2, 4), warmup=1
            )
        finally:
            tmp.cleanup()

        self.assertEqual(len(rows), 3)  # 1 cold + 2 warm 批量
        cold = rows[0]
        self.assertEqual((cold["mode"], cold["batch_size"]), ("cold", 1))
        warm_sizes = [row["batch_size"] for row in rows[1:]]
        self.assertEqual(warm_sizes, [2, 4])
        for row in rows:
            self.assertGreater(row["train_time_seconds"], 0.0)
            self.assertGreater(row["peak_memory_mb"], 0.0)
            self.assertGreater(row["artifact_bytes"], 0)
            self.assertGreaterEqual(row["load_time_seconds"], 0.0)
            self.assertGreater(row["mean_ms"], 0.0)
            self.assertGreater(row["throughput_per_s"], 0.0)
            self.assertEqual(row["training_samples"], 9)  # 12 工况随机留出 80%

        with tempfile.TemporaryDirectory() as out:
            paths = save_benchmark_report(
                rows, out, "benchmark_F", level="F", data_dir="synthetic"
            )
            self.assertTrue(all(path.is_file() for path in paths.values()))
            frame = pd.read_csv(paths["csv"])
            self.assertEqual(len(frame), 3)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(payload["n_rows"], 3)
            self.assertIn("rbf", paths["md"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
