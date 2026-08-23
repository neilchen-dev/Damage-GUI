"""瞄准物理扩展测试：相关散布核、旋转椭圆协方差与 Monte Carlo 独立验证。

覆盖：
- rotation_to_covariance 的三角恒等式与边界情形
- correlated_gaussian_kernel 的归一化、方向性与 rho=0 一致性
- optimize_aim 的 rho / theta_deg 参数化与参数校验
- Monte Carlo 期望毁伤效能与解析卷积价值场的一致性（不同数学路径互证）
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.optimization.aim import (
    correlated_gaussian_kernel,
    compute_aim_value_field_from_sigmas,
    gaussian_sampled_probability_kernel,
    monte_carlo_expected_damage,
    optimize_aim,
    rotation_to_covariance,
    value_at_physical_aim,
)


def smooth_gaussian_field(extent=50.0, n=201, sigma=8.0):
    axis = np.linspace(-extent, extent, n)
    grid_x, grid_y = np.meshgrid(axis, axis)
    return np.exp(-(grid_x**2 + grid_y**2) / (2.0 * sigma**2)), axis


class RotationCovarianceTests(unittest.TestCase):
    def test_theta_zero_returns_axes(self) -> None:
        sigma_x, sigma_y, rho = rotation_to_covariance(6.0, 3.0, 0.0)
        self.assertAlmostEqual(sigma_x, 6.0)
        self.assertAlmostEqual(sigma_y, 3.0)
        self.assertAlmostEqual(rho, 0.0)

    def test_45_degrees_gives_symmetric_sigmas(self) -> None:
        sigma_x, sigma_y, rho = rotation_to_covariance(6.0, 3.0, math.pi / 4)
        self.assertAlmostEqual(sigma_x, sigma_y, places=9)
        # σx=σy=√22.5，ρ=(σu²−σv²)·sinθcosθ/(σxσy) = 13.5/22.5 = 0.6
        self.assertAlmostEqual(rho, 0.6, places=9)

    def test_minus_45_flips_rho_sign(self) -> None:
        pos = rotation_to_covariance(6.0, 3.0, math.pi / 4)
        neg = rotation_to_covariance(6.0, 3.0, -math.pi / 4)
        self.assertAlmostEqual(pos[0], neg[0])
        self.assertAlmostEqual(pos[1], neg[1])
        self.assertAlmostEqual(pos[2], -neg[2])

    def test_variance_is_rotation_invariant(self) -> None:
        """总方差 trace(Σ) = σu² + σv² 不随旋转角变化。"""
        for theta in (0.3, 1.1, -0.7, 2.5):
            sigma_x, sigma_y, _rho = rotation_to_covariance(5.0, 2.0, theta)
            self.assertAlmostEqual(sigma_x**2 + sigma_y**2, 25.0 + 4.0, places=9)

    def test_90_degrees_swaps_axes(self) -> None:
        sigma_x, sigma_y, rho = rotation_to_covariance(6.0, 3.0, math.pi / 2)
        self.assertAlmostEqual(sigma_x, 3.0, places=9)
        self.assertAlmostEqual(sigma_y, 6.0, places=9)
        self.assertAlmostEqual(rho, 0.0, places=9)

    def test_degenerate_input(self) -> None:
        sigma_x, sigma_y, rho = rotation_to_covariance(0.0, 0.0, 0.5)
        self.assertEqual((sigma_x, sigma_y, rho), (0.0, 0.0, 0.0))

    def test_single_axis_degenerate_input_preserves_nonzero_axis(self) -> None:
        self.assertEqual(
            rotation_to_covariance(0.0, 2.0, 0.0),
            (0.0, 2.0, 0.0),
        )
        sigma_x, sigma_y, rho = rotation_to_covariance(2.0, 0.0, math.pi / 2)
        self.assertAlmostEqual(sigma_x, 0.0, places=9)
        self.assertAlmostEqual(sigma_y, 2.0, places=9)
        self.assertAlmostEqual(rho, 0.0, places=9)

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            rotation_to_covariance(-1.0, 2.0, 0.0)
        with self.assertRaises(ValueError):
            rotation_to_covariance(1.0, 2.0, float("nan"))


class CorrelatedKernelTests(unittest.TestCase):
    def test_kernel_normalizes_to_one(self) -> None:
        for rho in (-0.8, -0.3, 0.0, 0.5, 0.9):
            kernel = correlated_gaussian_kernel(2.0, 1.5, rho, 1.0, 1.0)
            self.assertAlmostEqual(float(kernel.sum()), 1.0, places=9)

    def test_kernel_is_sidelobe_free(self) -> None:
        """马氏截断外严格为 0。"""
        kernel = correlated_gaussian_kernel(2.0, 1.5, 0.6, 1.0, 1.0, truncate=4.0)
        # 中心在 (half, half)
        center = np.unravel_index(int(np.argmax(kernel)), kernel.shape)
        offset_y, offset_x = np.mgrid[0 : kernel.shape[0], 0 : kernel.shape[1]]
        dy = (offset_y - center[0]) * 1.0
        dx = (offset_x - center[1]) * 1.0
        zx, zy = dx / 2.0, dy / 1.5
        mahalanobis_sq = (zx**2 - 2 * 0.6 * zx * zy + zy**2) / (1 - 0.36)
        outside = mahalanobis_sq > 16.0 + 1e-9
        self.assertTrue(np.all(kernel[outside] == 0.0))

    def test_positive_rho_tilts_kernel_along_plus_diagonal(self) -> None:
        """ρ>0 的核质量沿 (+x, +y) 对角线方向延展。"""
        kernel = correlated_gaussian_kernel(3.0, 3.0, 0.8, 1.0, 1.0)
        center = np.array(kernel.shape) // 2
        # 比较两个对角带内的质量：主对角 (+1,+1) 方向 vs 反对角 (+1,-1)
        main_diag = kernel[center[0] + 1 :, center[1] + 1 :].sum()
        anti_diag = kernel[center[0] + 1 :, : center[1]].sum()
        self.assertGreater(main_diag, anti_diag * 1.5)

    def test_rho_zero_matches_sampled_kernel(self) -> None:
        """ρ=0 时与 sampled 核一致（差异仅来自截断窗口形状，< 1e-4）。"""
        k1 = correlated_gaussian_kernel(2.0, 2.0, 0.0, 1.0, 1.0)
        k2 = gaussian_sampled_probability_kernel(2.0, 2.0, 1.0, 1.0)
        np.testing.assert_allclose(k1, k2, atol=1e-4)

    def test_invalid_rho_rejected(self) -> None:
        for rho in (1.0, -1.0, float("nan"), 2.0):
            with self.assertRaises(ValueError):
                correlated_gaussian_kernel(1.0, 1.0, rho, 1.0, 1.0)


class OptimizeAimCorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.damage, cls.axis = smooth_gaussian_field()

    def test_rho_passthrough_to_result_and_field(self) -> None:
        result = optimize_aim(
            self.damage, self.axis, self.axis,
            spread_mode="REP_DEP", rep=6.745, dep=4.047, rho=0.4,
        )
        self.assertAlmostEqual(result.rho, 0.4)
        # 与显式调用 value_field 计算一致
        value_field, _ = compute_aim_value_field_from_sigmas(
            self.damage, result.sigma_x, result.sigma_y,
            float(self.axis[0]), float(self.axis[-1]), 1.0, "sampled", rho=0.4,
        )
        np.testing.assert_allclose(result.value_field, value_field, atol=1e-12)

    def test_theta_rotates_sigma_to_expected_covariance(self) -> None:
        # rep=6.745 → σu=10；dep=4.047 → σv=6；θ=90° → σx=6, σy=10
        result = optimize_aim(
            self.damage, self.axis, self.axis,
            spread_mode="REP_DEP", rep=6.745, dep=4.047, theta_deg=90.0,
        )
        self.assertAlmostEqual(result.sigma_x, 6.0, places=6)
        self.assertAlmostEqual(result.sigma_y, 10.0, places=6)
        self.assertAlmostEqual(result.rho, 0.0, places=6)

    def test_45_degree_rotation_symmetry(self) -> None:
        """对称圆形 D 场上，θ=+45° 与 θ=−45° 的 Vmax 应相等。"""
        pos = optimize_aim(
            self.damage, self.axis, self.axis,
            spread_mode="REP_DEP", rep=6.745, dep=4.047, theta_deg=45.0,
        )
        neg = optimize_aim(
            self.damage, self.axis, self.axis,
            spread_mode="REP_DEP", rep=6.745, dep=4.047, theta_deg=-45.0,
        )
        self.assertAlmostEqual(pos.vmax, neg.vmax, places=9)

    def test_cep_mode_rejects_correlation(self) -> None:
        with self.assertRaises(ValueError):
            optimize_aim(
                self.damage, self.axis, self.axis,
                spread_mode="CEP", cep=5.0, rho=0.3,
            )
        with self.assertRaises(ValueError):
            optimize_aim(
                self.damage, self.axis, self.axis,
                spread_mode="CEP", cep=5.0, theta_deg=30.0,
            )


class MonteCarloValidationTests(unittest.TestCase):
    def test_mc_matches_analytic_convolution_for_independent_spread(self) -> None:
        """ρ=0：MC 估计与解析卷积一致（独立数学路径互证）。"""
        damage, axis = smooth_gaussian_field()
        sigma_x = sigma_y = 4.0
        value_field, _ = compute_aim_value_field_from_sigmas(
            damage, sigma_x, sigma_y, float(axis[0]), float(axis[-1]), 1.0,
            "cell_integrated",
        )
        aim_x, aim_y = 3.0, -2.0
        analytic = value_at_physical_aim(
            value_field, aim_x, aim_y, float(axis[0]), float(axis[-1])
        )
        mc = monte_carlo_expected_damage(
            damage, axis, axis, aim_x, aim_y, sigma_x, sigma_y,
            n_samples=60000, random_state=42,
        )
        tolerance = 5.0 * mc.std_error + 5e-3
        self.assertAlmostEqual(
            mc.mean, analytic, delta=tolerance,
            msg=f"analytic={analytic:.5f}, mc={mc.mean:.5f}±{mc.std_error:.5f}",
        )

    def test_mc_matches_analytic_convolution_for_correlated_spread(self) -> None:
        """ρ=0.5：相关散布下 MC 与解析卷积一致。"""
        damage, axis = smooth_gaussian_field()
        sigma_x, sigma_y, rho = 5.0, 3.0, 0.5
        value_field, _ = compute_aim_value_field_from_sigmas(
            damage, sigma_x, sigma_y, float(axis[0]), float(axis[-1]), 1.0,
            "sampled", rho=rho,
        )
        aim_x, aim_y = 4.0, 3.0
        analytic = value_at_physical_aim(
            value_field, aim_x, aim_y, float(axis[0]), float(axis[-1])
        )
        mc = monte_carlo_expected_damage(
            damage, axis, axis, aim_x, aim_y, sigma_x, sigma_y, rho=rho,
            n_samples=80000, random_state=7,
        )
        tolerance = 5.0 * mc.std_error + 5e-3
        self.assertAlmostEqual(
            mc.mean, analytic, delta=tolerance,
            msg=f"analytic={analytic:.5f}, mc={mc.mean:.5f}±{mc.std_error:.5f}",
        )

    def test_mc_reliability_scales_mean(self) -> None:
        damage, axis = smooth_gaussian_field(extent=30.0, n=121, sigma=6.0)
        base = monte_carlo_expected_damage(
            damage, axis, axis, 0.0, 0.0, 3.0, 3.0,
            n_samples=20000, random_state=1,
        )
        scaled = monte_carlo_expected_damage(
            damage, axis, axis, 0.0, 0.0, 3.0, 3.0,
            n_samples=20000, random_state=1, reliability=0.7,
        )
        self.assertAlmostEqual(scaled.mean, 0.7 * base.mean, places=6)

    def test_mc_outside_grid_damage_is_zero(self) -> None:
        damage, axis = smooth_gaussian_field(extent=20.0, n=81, sigma=3.0)
        # 瞄准点远离网格：σ 极小时所有落点都在网格外
        mc = monte_carlo_expected_damage(
            damage, axis, axis, 1000.0, 1000.0, 0.05, 0.05,
            n_samples=2000, random_state=3,
        )
        self.assertAlmostEqual(mc.mean, 0.0, places=12)

    def test_mc_deterministic_with_seed(self) -> None:
        damage, axis = smooth_gaussian_field(extent=30.0, n=121, sigma=6.0)
        first = monte_carlo_expected_damage(
            damage, axis, axis, 1.0, 2.0, 3.0, 2.0, rho=0.2,
            n_samples=5000, random_state=11,
        )
        second = monte_carlo_expected_damage(
            damage, axis, axis, 1.0, 2.0, 3.0, 2.0, rho=0.2,
            n_samples=5000, random_state=11,
        )
        self.assertEqual(first.mean, second.mean)

    def test_invalid_arguments_raise(self) -> None:
        damage, axis = smooth_gaussian_field(extent=10.0, n=41, sigma=2.0)
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, axis, axis, 0.0, 0.0, 1.0, 1.0, n_samples=0,
            )
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, axis, axis, 0.0, 0.0, 1.0, 1.0, reliability=1.5,
            )
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, axis, axis, 0.0, 0.0, 1.0, 1.0, rho=1.0,
            )
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, axis, axis, 0.0, 0.0, -1.0, 1.0,
            )
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, axis, axis, 0.0, 0.0, float("nan"), 1.0,
            )
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, axis[:-1], axis, 0.0, 0.0, 1.0, 1.0,
            )
        nonuniform = axis.copy()
        nonuniform[len(nonuniform) // 2] += 0.1
        with self.assertRaises(ValueError):
            monte_carlo_expected_damage(
                damage, nonuniform, axis, 0.0, 0.0, 1.0, 1.0,
            )


if __name__ == "__main__":
    unittest.main()
