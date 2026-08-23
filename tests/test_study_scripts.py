"""实验脚本的轻量回归测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ablation_study import evaluate_focus
from calibrate_ood import normalized_steps, recommend_thresholds, validation_errors
from damage_gui.data.loader import Condition
from damage_gui.data.loader import DamageRecord

import pandas as pd


class _ConstantModel:
    def __init__(self, value: float, shape: tuple[int, int]):
        self.value = value
        self.shape = shape
        self.conditions: list[Condition] = []

    def predict_matrix(self, condition: Condition) -> np.ndarray:
        if not isinstance(condition, Condition):
            raise TypeError("实验脚本必须把数值工况转换为 Condition")
        self.conditions.append(condition)
        return np.full(self.shape, self.value, dtype=np.float32)


class StudyScriptTests(unittest.TestCase):
    def test_ablation_converts_numeric_conditions_for_prediction(self) -> None:
        shape = (16, 16)
        model = _ConstantModel(0.5, shape)
        conditions = np.array([[1.0, 100.0, 10.0], [2.0, 200.0, 20.0]])
        truths = np.full((2, *shape), 0.5, dtype=np.float32)

        row, predict_time = evaluate_focus(model, conditions, truths)

        self.assertEqual(len(model.conditions), 2)
        self.assertAlmostEqual(float(row["MeanRelativeError"]), 0.0)
        self.assertAlmostEqual(float(row["P95HybridError"]), 0.0)
        self.assertGreaterEqual(predict_time, 0.0)

    def test_ood_calibration_matches_grid_and_validation_errors(self) -> None:
        records = [
            DamageRecord("F", Condition(h, v, deg), Path("unused"))
            for h in (0.0, 1.0, 2.0, 3.0, 4.0)
            for v in (150.0, 200.0, 250.0, 300.0)
            for deg in (20.0, 25.0, 30.0, 35.0, 40.0, 45.0)
        ]
        frame = pd.DataFrame(
            {
                "Validation": [
                    "按高度整层留出 Leave-h-out",
                    "按速度整层留出 Leave-v-out",
                    "按角度整层留出 Leave-deg-out",
                ],
                "MeanRE": [0.0919, 0.1528, 0.0810],
                "P95Hybrid": [0.1724, 0.2440, 0.1657],
            }
        )

        steps = normalized_steps(records)
        errors = validation_errors(frame)
        high, medium = recommend_thresholds(steps, errors, target=0.20)

        self.assertAlmostEqual(steps["h"], 0.25)
        self.assertAlmostEqual(steps["v"], 1.0 / 3.0)
        self.assertAlmostEqual(steps["deg"], 0.20)
        self.assertAlmostEqual(high, 0.15)
        self.assertAlmostEqual(medium, (0.25 + 1.0 / 3.0) / 2.0)


if __name__ == "__main__":
    unittest.main()
