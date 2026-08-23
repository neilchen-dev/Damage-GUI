"""数值回归测试：固定种子合成集上的黄金值对比。

容差策略（勿随手放宽；先记录实际差异，再决定容差）：
- 本机 Windows 双进程实测最大漂移 = 0.0（95 个数值条目，full-SVD 确定性路径）；
- 跨 Windows/Linux 的唯一预期差异源是 OpenBLAS/LAPACK 内核选择的浮点舍入
  （量级 ~1e-12 至 1e-8），容差取 1e-6（场摘要/指标）与 1e-9（纯算术项），
  高于预期抖动约 2 个数量级，远低于任何真实算法回归（≥1e-3）；
- CI 的 Windows/Linux 双平台运行为最终权威：若某平台失败，失败信息会打印
  实际偏差，依据实测证据调整下方常量（一处修改）；
- 禁止为了让测试通过而重新生成黄金值或放宽容差而不给出漂移证据。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regression_tools import (  # noqa: E402
    GOLDEN_PATH,
    PROBES,
    build_snapshot_in_tempdir,
)

FIELD_TOL = 1e-6     # 预测场摘要（max/mean/sum/采样像素），值域 O(1)
METRIC_TOL = 1e-6    # MeanRE / P95 Hybrid 核心指标
EV_TOL = 1e-9        # POD 累计解释方差（≈1.0 的比值求和）
OOD_TOL = 1e-9       # OOD 最近工况距离（纯算术，无 BLAS）


class NumericalRegressionTests(unittest.TestCase):
    """相同输入 → 相同预测/模态/OOD/指标（允许容差内浮点漂移）。"""

    @classmethod
    def setUpClass(cls) -> None:
        if not GOLDEN_PATH.is_file():
            raise unittest.SkipTest(
                f"黄金值文件不存在: {GOLDEN_PATH}，"
                "请先运行 scripts/regen_regression_golden.py 并提交"
            )
        cls.golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        cls.snapshot, cls._tmp = build_snapshot_in_tempdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # ---------- 对比辅助 ----------

    @staticmethod
    def _diff(actual, expected) -> float:
        return abs(float(actual) - float(expected))

    def _assert_close(self, actual, expected, tol: float, label: str) -> None:
        diff = self._diff(actual, expected)
        self.assertLessEqual(
            diff, tol,
            f"{label}: 实际 {actual!r} vs 黄金 {expected!r}，"
            f"偏差 {diff:.3e} 超过容差 {tol:.0e}",
        )

    # ---------- 用例 ----------

    def test_prediction_fields_are_stable(self) -> None:
        """相同输入的预测结果在容差内稳定（RBF 与 POD-RBF 双模型）。"""
        for model_key in ("rbf", "pod_rbf"):
            golden_probes = self.golden[model_key]["probes"]
            actual_probes = self.snapshot[model_key]["probes"]
            for probe_name, _, _, _ in PROBES:
                golden = golden_probes[probe_name]
                actual = actual_probes[probe_name]
                for stat in ("max", "mean", "sum"):
                    self._assert_close(
                        actual[stat], golden[stat], FIELD_TOL,
                        f"{model_key}.{probe_name}.{stat}",
                    )
                for index, (a, g) in enumerate(
                    zip(actual["samples"], golden["samples"], strict=True)
                ):
                    self._assert_close(
                        a, g, FIELD_TOL, f"{model_key}.{probe_name}.samples[{index}]"
                    )

    def test_pod_modes_do_not_drift(self) -> None:
        """POD 累计解释方差与实际使用的模态数不发生漂移。"""
        golden = self.golden["pod_rbf"]
        actual = self.snapshot["pod_rbf"]
        self._assert_close(
            actual["explained_variance"], golden["explained_variance"],
            EV_TOL, "pod_rbf.explained_variance",
        )
        self.assertEqual(
            actual["n_components_used"], golden["n_components_used"],
            "POD 实际使用模态数发生变化",
        )

    def test_ood_classification_is_stable(self) -> None:
        """OOD 分级不意外变化；最近工况距离容差内一致。"""
        for probe_name, _, _, _ in PROBES:
            golden = self.golden["ood"][probe_name]
            actual = self.snapshot["ood"][probe_name]
            self._assert_close(
                actual["distance"], golden["distance"], OOD_TOL,
                f"ood.{probe_name}.distance",
            )
            self.assertEqual(
                actual["level"], golden["level"],
                f"ood.{probe_name}.level 分级发生变化",
            )

    def test_core_metrics_do_not_regress(self) -> None:
        """核心指标（MeanRE / P95 Hybrid）计算不发生回归。"""
        for model_key in ("rbf", "pod_rbf"):
            golden = self.golden[model_key]["core_metrics"]
            actual = self.snapshot[model_key]["core_metrics"]
            for metric in ("mean_relative_error", "p95_hybrid_error"):
                self._assert_close(
                    actual[metric], golden[metric], METRIC_TOL,
                    f"{model_key}.core_metrics.{metric}",
                )


if __name__ == "__main__":
    unittest.main()
