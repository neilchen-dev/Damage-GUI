"""结构化交叉验证切分测试。"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition, DamageRecord
from damage_gui.model.validation import make_splits


def synthetic_records():
    """3 高度 × 2 速度 × 2 角度 = 12 条记录。"""
    records = []
    for h in (1.0, 2.0, 3.0):
        for v in (100.0, 200.0):
            for deg in (10.0, 20.0):
                records.append(
                    DamageRecord(
                        level="F",
                        condition=Condition(h=h, v=v, deg=deg),
                        path=Path(f"synthetic_h{h}_v{v}_deg{deg}"),
                    )
                )
    return records


class ValidationSplitTests(unittest.TestCase):
    def test_random_split_covers_all_records(self) -> None:
        records = synthetic_records()
        splits = make_splits(records, "random", CONFIG)
        self.assertEqual(len(splits), 1)
        split = splits[0]
        self.assertEqual(len(split.train) + len(split.test), len(records))
        self.assertFalse(set(split.train) & set(split.test))
        self.assertTrue(set(split.train) | set(split.test) == set(records))

    def test_leave_h_out_produces_one_split_per_height(self) -> None:
        records = synthetic_records()
        splits = make_splits(records, "leave_h_out", CONFIG)
        self.assertEqual(len(splits), 3)
        all_test = []
        for split in splits:
            heights = {record.condition.h for record in split.test}
            self.assertEqual(len(heights), 1, "每个折只测试一个高度层")
            train_heights = {record.condition.h for record in split.train}
            self.assertNotIn(next(iter(heights)), train_heights, "训练集不得包含测试层")
            all_test.extend(split.test)
        # 所有折的测试集合并 = 全部工况，且互不重复
        self.assertEqual(len(all_test), len(records))
        self.assertEqual(len({record.condition.as_key() for record in all_test}), len(records))

    def test_leave_v_out_and_leave_deg_out(self) -> None:
        records = synthetic_records()
        self.assertEqual(len(make_splits(records, "leave_v_out", CONFIG)), 2)
        self.assertEqual(len(make_splits(records, "leave_deg_out", CONFIG)), 2)

    def test_corner_split_excludes_high_speed_large_angle_region(self) -> None:
        records = synthetic_records()
        config = dataclasses.replace(CONFIG, corner_v_min=150.0, corner_deg_min=15.0)
        splits = make_splits(records, "corner", config)
        self.assertEqual(len(splits), 1)
        split = splits[0]
        expected_test = {
            record.condition.as_key()
            for record in records
            if record.condition.v >= 150.0 and record.condition.deg >= 15.0
        }
        actual_test = {record.condition.as_key() for record in split.test}
        self.assertEqual(actual_test, expected_test)
        self.assertEqual(len(expected_test), 3)  # v=200 & deg=20 的 3 个高度
        for record in split.train:
            self.assertFalse(
                record.condition.v >= 150.0 and record.condition.deg >= 15.0,
                "训练集不得包含角落区域",
            )

    def test_corner_split_raises_when_region_empty(self) -> None:
        records = synthetic_records()
        config = dataclasses.replace(CONFIG, corner_v_min=999.0, corner_deg_min=999.0)
        with self.assertRaises(ValueError):
            make_splits(records, "corner", config)

    def test_corner_split_raises_when_region_covers_everything(self) -> None:
        records = synthetic_records()
        config = dataclasses.replace(CONFIG, corner_v_min=0.0, corner_deg_min=0.0)
        with self.assertRaisesRegex(ValueError, "全部工况"):
            make_splits(records, "corner", config)

    def test_leave_mode_requires_multiple_values(self) -> None:
        records = [
            DamageRecord("F", Condition(h=1.0, v=v, deg=10.0), Path(f"r{v}"))
            for v in (100.0, 200.0)
        ]
        with self.assertRaises(ValueError):
            make_splits(records, "leave_h_out", CONFIG)

    def test_unknown_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            make_splits(synthetic_records(), "unknown_mode", CONFIG)


if __name__ == "__main__":
    unittest.main()
