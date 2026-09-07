"""M3.7 Hypothesis property-based 测试：纯函数单元的不变量检查。

只覆盖确定性、无副作用的单元（不触碰训练管线与数值回归口径）：
- 预测场输出契约：float32 / target_shape / [0,1] / ROI 外恒 0
  （最近邻基线与 RBF 场，含退化训练集的 span 防护）；
- 最近邻基线对训练工况的精确复现；
- 不确定度估计器的边界（距离非负、残差均值不越界、k 截断）；
- 校准分箱的样本守恒与常量输入退化；
- Spearman 守卫（常量输入 → NaN）与单调输入的相关系数边界;
- 评估口径：同一场对自身误差恒为 0。
"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from damage_gui.config import CONFIG  # noqa: E402
from damage_gui.data.loader import Condition  # noqa: E402
from damage_gui.data.preprocessing import roi_mask_for_shape  # noqa: E402
from damage_gui.experiments.baselines import NearestNeighborField  # noqa: E402
from damage_gui.experiments.uncertainty import (  # noqa: E402
    UncertaintyEstimator,
    _spearman,
    calibration_bins,
    sample_roi_mae,
)
from damage_gui.model.rbf import RBFDamageField  # noqa: E402

SHAPE = (16, 16)
TEST_CONFIG = dataclasses.replace(CONFIG, target_shape=SHAPE, eval_smoothing_sigma=1.0)
ROI = roi_mask_for_shape(SHAPE, TEST_CONFIG)
FAST = settings(max_examples=30, deadline=None)

finite_float = st.floats(allow_nan=False, allow_infinity=False)
condition_st = st.builds(
    Condition,
    h=st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    v=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    deg=st.floats(min_value=0.0, max_value=90.0, allow_nan=False, allow_infinity=False),
)


def bump_matrix(amplitude: float, center_r: float, center_c: float) -> np.ndarray:
    rows, cols = np.indices(SHAPE, dtype=float)
    field = amplitude * np.exp(
        -((rows - center_r) ** 2 + (cols - center_c) ** 2) / (2.0 * 2.0 ** 2)
    )
    return np.clip(field, 0.0, 1.0).astype(np.float32)


def assert_output_contract(case: unittest.TestCase, matrix: np.ndarray) -> None:
    case.assertEqual(matrix.dtype, np.float32)
    case.assertEqual(matrix.shape, SHAPE)
    case.assertTrue(np.all((matrix >= 0.0) & (matrix <= 1.0)))
    case.assertTrue(np.all(matrix[~ROI] == 0.0))


TRAIN_CONDITIONS = np.array(
    [(h, v, deg)
     for h in (1.0, 2.0) for v in (100.0, 200.0) for deg in (10.0, 20.0)],
    dtype=np.float64,
)
TRAIN_MATRICES = np.stack([
    bump_matrix(0.3 + 0.06 * i, 6.0 + (i % 3), 7.0 + (i % 2))
    for i in range(len(TRAIN_CONDITIONS))
])


class NearestNeighborPropertyTests(unittest.TestCase):
    """最近邻基线：输出契约 + 训练工况精确复现 + 退化训练集防护。"""

    @classmethod
    def setUpClass(cls):
        cls.model = NearestNeighborField(SHAPE, config=TEST_CONFIG)
        cls.model.fit(TRAIN_CONDITIONS, TRAIN_MATRICES)

    @FAST
    @given(condition_st)
    def test_output_contract_any_query(self, condition: Condition) -> None:
        assert_output_contract(self, self.model.predict_matrix(condition))

    @given(st.integers(min_value=0, max_value=len(TRAIN_CONDITIONS) - 1))
    def test_exact_recall_at_training_conditions(self, index: int) -> None:
        h, v, deg = TRAIN_CONDITIONS[index]
        pred = self.model.predict_matrix(Condition(h, v, deg))
        expected = np.clip(TRAIN_MATRICES[index].astype(np.float32), 0.0, 1.0)
        expected[~ROI] = 0.0
        np.testing.assert_array_equal(pred, expected)

    @FAST
    @given(condition_st)
    def test_degenerate_training_set_span_guard(self, condition: Condition) -> None:
        """全部训练工况相同（span=0）时防护应生效而不是除零。"""
        model = NearestNeighborField(SHAPE, config=TEST_CONFIG)
        single = TRAIN_CONDITIONS[:1]
        model.fit(np.repeat(single, 3, axis=0), np.repeat(TRAIN_MATRICES[:1], 3, axis=0))
        self.assertTrue(np.all(model.cond_span > 0.0))
        assert_output_contract(self, model.predict_matrix(condition))


@st.composite
def estimator_inputs(draw):
    n = draw(st.integers(min_value=1, max_value=6))
    conditions = np.array([
        [
            draw(st.floats(min_value=0.0, max_value=500.0,
                           allow_nan=False, allow_infinity=False)),
            draw(st.floats(min_value=0.0, max_value=1000.0,
                           allow_nan=False, allow_infinity=False)),
            draw(st.floats(min_value=0.0, max_value=90.0,
                           allow_nan=False, allow_infinity=False)),
        ]
        for _ in range(n)
    ])
    residuals = np.array(draw(st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=n, max_size=n,
    )))
    k = draw(st.integers(min_value=1, max_value=n + 2))  # 覆盖 k>样本数的截断分支
    return conditions, residuals, k


class UncertaintyEstimatorPropertyTests(unittest.TestCase):
    @FAST
    @given(estimator_inputs(), condition_st)
    def test_estimate_bounds(self, inputs, condition: Condition) -> None:
        conditions, residuals, k = inputs
        estimator = UncertaintyEstimator(conditions, residuals, k=k)
        distance = estimator.knn_distance(condition)
        self.assertTrue(np.isfinite(distance) and distance >= 0.0)
        estimate = estimator.residual_knn(condition)
        self.assertGreaterEqual(estimate, residuals.min() - 1e-12)
        self.assertLessEqual(estimate, residuals.max() + 1e-12)

    @given(st.integers(min_value=0, max_value=5))
    def test_zero_distance_at_training_point(self, index: int) -> None:
        estimator = UncertaintyEstimator(TRAIN_CONDITIONS, np.zeros(8), k=1)
        h, v, deg = TRAIN_CONDITIONS[index]
        self.assertEqual(estimator.knn_distance(Condition(h, v, deg)), 0.0)


@st.composite
def estimate_error_pairs(draw):
    n = draw(st.integers(min_value=1, max_value=60))
    estimates = np.array(draw(st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=n, max_size=n,
    )))
    errors = np.array(draw(st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=n, max_size=n,
    )))
    return estimates, errors


class CalibrationBinsPropertyTests(unittest.TestCase):
    @FAST
    @given(estimate_error_pairs(), st.integers(min_value=2, max_value=6))
    def test_sample_conservation_and_bounds(self, pair, n_bins: int) -> None:
        estimates, errors = pair
        bins = calibration_bins(estimates, errors, n_bins)
        self.assertEqual(int(bins["n"].sum()), len(estimates))
        self.assertLessEqual(len(bins), max(n_bins, 1))
        self.assertGreaterEqual(bins["mean_estimate"].min(), estimates.min() - 1e-9)
        self.assertLessEqual(bins["mean_estimate"].max(), estimates.max() + 1e-9)
        self.assertGreaterEqual(bins["mean_error"].min(), errors.min() - 1e-9)
        self.assertLessEqual(bins["mean_error"].max(), errors.max() + 1e-9)

    @given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
           st.integers(min_value=2, max_value=80))
    def test_constant_estimates_collapse_to_single_bin(
        self, value: float, n: int
    ) -> None:
        errors = np.linspace(0.0, 1.0, n)
        bins = calibration_bins(np.full(n, value), errors, 4)
        self.assertEqual(len(bins), 1)
        self.assertEqual(int(bins.iloc[0]["n"]), n)
        self.assertAlmostEqual(float(bins.iloc[0]["mean_estimate"]), value, places=12)
        self.assertAlmostEqual(
            float(bins.iloc[0]["mean_error"]), float(errors.mean()), places=12
        )


class SpearmanGuardPropertyTests(unittest.TestCase):
    @FAST
    @given(estimate_error_pairs())
    def test_result_is_nan_or_valid_correlation(self, pair) -> None:
        estimates, errors = pair
        rho = _spearman(estimates, errors)
        self.assertTrue(np.isnan(rho) or -1.0 <= rho <= 1.0)

    @given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
           st.integers(min_value=2, max_value=30))
    def test_constant_input_is_nan(self, value: float, n: int) -> None:
        estimates = np.full(n, value)
        errors = np.linspace(0.0, 1.0, n)
        self.assertTrue(np.isnan(_spearman(estimates, errors)))
        self.assertTrue(np.isnan(_spearman(errors, estimates)))

    @given(st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=2, max_size=40, unique=True,
    ))
    def test_monotone_input_reaches_correlation_bounds(self, values) -> None:
        ordered = np.array(sorted(values))
        self.assertAlmostEqual(_spearman(ordered, ordered.copy()), 1.0, places=10)
        self.assertAlmostEqual(_spearman(ordered, -ordered), -1.0, places=10)


class EvaluationCaliberPropertyTests(unittest.TestCase):
    @FAST
    @given(
        st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=4.0, max_value=11.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=4.0, max_value=11.0, allow_nan=False, allow_infinity=False),
    )
    def test_identical_field_has_zero_error(self, amplitude, center_r, center_c) -> None:
        matrix = bump_matrix(amplitude, center_r, center_c)
        self.assertEqual(sample_roi_mae(matrix, matrix.copy(), TEST_CONFIG), 0.0)


class RBFFieldPropertyTests(unittest.TestCase):
    """RBF 场输出契约（含质心对齐分支）：训练集固定，查询任意。"""

    @classmethod
    def setUpClass(cls):
        # 归一化后 4 个不共面工况，thin_plate_spline 精确插值合法
        conditions = np.array(
            [(1.0, 100.0, 10.0), (1.0, 200.0, 20.0),
             (2.0, 100.0, 20.0), (2.0, 200.0, 10.0)],
            dtype=np.float64,
        )
        matrices = np.stack([
            bump_matrix(0.4 + 0.1 * i, 6.0 + i * 0.5, 7.0 + i * 0.3) for i in range(4)
        ])
        cls.model = RBFDamageField(
            TEST_CONFIG.rbf_kernel, 0.0, SHAPE, align=True, config=TEST_CONFIG
        )
        cls.model.fit(conditions, matrices)

    @FAST
    @given(condition_st)
    def test_output_contract_any_query(self, condition: Condition) -> None:
        assert_output_contract(self, self.model.predict_matrix(condition))


if __name__ == "__main__":
    unittest.main()
