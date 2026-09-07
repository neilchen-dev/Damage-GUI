"""M3.5 SQLite 实验追踪的回归测试（纯持久层，无需训练）。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui.experiments.runner import ExperimentResult  # noqa: E402
from damage_gui.experiments.tracking import (  # noqa: E402
    ExperimentStore,
    compare_runs,
)


def make_result(
    name: str, *, suite: str = "design", mre: float, status: str = "ok"
) -> ExperimentResult:
    return ExperimentResult(
        experiment=name,
        suite=suite,
        level="F",
        model_type="rbf",
        validation_mode="random",
        align_patterns=True,
        rbf_kernel="thin_plate_spline",
        rbf_smoothing=0.0,
        rbf_epsilon=None,
        pod_n_components=None,
        seed=42,
        status=status,
        metrics={"mean_relative_error": mre, "r2": 0.9},
        train_time_seconds=1.5,
    )


class StoreTests(unittest.TestCase):
    def test_record_list_get_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "experiments.sqlite3"
            with ExperimentStore(db) as store:
                ids = store.record(
                    [
                        make_result("a", mre=0.1),
                        make_result("b", mre=0.2, status="error"),
                    ],
                    suite="design",
                )
                self.assertEqual(ids, [1, 2])

                frame = store.list_runs()
                self.assertEqual(list(frame["id"]), [2, 1])  # 新记录在前
                self.assertEqual(frame.iloc[0]["experiment"], "b")
                self.assertEqual(frame.iloc[0]["status"], "error")
                self.assertAlmostEqual(frame.iloc[1]["mean_relative_error"], 0.1)

                payload = store.get_run(1)
                self.assertEqual(payload["experiment"], "a")
                self.assertEqual(payload["suite"], "design")
                self.assertAlmostEqual(payload["mean_relative_error"], 0.1)
                self.assertNotIn("metrics", payload)  # 指标已扁平化

            # 重新打开：数据持久
            with ExperimentStore(db) as store:
                self.assertEqual(len(store.list_runs()), 2)

    def test_get_run_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ExperimentStore(Path(tmp) / "x.sqlite3") as store:
                with self.assertRaises(KeyError):
                    store.get_run(999)

    def test_compare_runs_side_by_side(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ExperimentStore(Path(tmp) / "x.sqlite3") as store:
                ids = store.record(
                    [make_result("a", mre=0.10), make_result("b", mre=0.20)]
                )
                frame = compare_runs(store, ids)
                self.assertEqual(frame.shape[1], 2)
                self.assertTrue(frame.index.isin(["experiment", "status"]).any())
                a_col = frame.columns[0]
                self.assertEqual(frame.loc["experiment", a_col], "a")
                self.assertAlmostEqual(
                    float(frame.loc["mean_relative_error", a_col]), 0.10
                )


if __name__ == "__main__":
    unittest.main()
