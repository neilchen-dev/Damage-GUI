"""Numerical regression tests for the standalone aim-optimization module."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.aim_optimization import (
    cep_to_sigma,
    compute_aim_value_field,
    find_best_aim_point,
    gaussian_cell_probability_kernel,
    rep_dep_to_sigma,
)


class AimOptimizationTests(unittest.TestCase):
    def test_dispersion_conversions(self) -> None:
        self.assertAlmostEqual(cep_to_sigma(11.774), 10.0, places=8)
        sigma_x, sigma_y = rep_dep_to_sigma(6.745, 13.49)
        self.assertAlmostEqual(sigma_x, 10.0, places=8)
        self.assertAlmostEqual(sigma_y, 20.0, places=8)

    def test_zero_dispersion_preserves_damage_field(self) -> None:
        damage = np.array([[0.1, 0.3], [0.5, 0.9]])
        value, kernel = compute_aim_value_field(damage, 0.0, -1.0, 1.0, reliability=0.8)
        np.testing.assert_allclose(kernel, [[1.0]])
        np.testing.assert_allclose(value, damage * 0.8)
        row, col, peak = find_best_aim_point(value)
        self.assertEqual((row, col), (1, 1))
        self.assertAlmostEqual(peak, 0.72)

    def test_probability_kernel_is_normalized(self) -> None:
        kernel = gaussian_cell_probability_kernel(10.0, 20.0, 2.0, 2.0)
        self.assertGreater(kernel.shape[0], kernel.shape[1])
        self.assertAlmostEqual(float(kernel.sum()), 1.0, places=12)
        self.assertGreater(float(kernel[kernel.shape[0] // 2, kernel.shape[1] // 2]), 0.0)


if __name__ == "__main__":
    unittest.main()
