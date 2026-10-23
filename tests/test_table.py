"""Table 与 pandas.DataFrame 的行为等价性测试。

这组用例是"用 damage_gui.data.table 替换核心链路 pandas"的安全网：
凡是与 pandas 语义不一致的地方都必须在开发期暴露，而不是等到
GUI/Web 运行时才炸。pandas 缺失时自动跳过（[core] 最小安装）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.data.table import Table, isna, notna, read_csv, to_numeric  # noqa: E402

try:
    import pandas as pd
except ImportError:  # pragma: no cover —— [core] 安装下跳过对照
    pd = None

ROWS = [
    {"scope": "damage_gt_0.05", "field": "smoothed", "MeanRelativeError": 0.12,
     "P95HybridError": 0.30, "IoU": np.nan},
    {"scope": "damage_gt_0.05", "field": "raw", "MeanRelativeError": 0.18,
     "P95HybridError": 0.36, "IoU": np.nan},
    {"scope": "spatial", "field": "raw", "MeanRelativeError": np.nan,
     "P95HybridError": np.nan, "IoU": 0.81},
]


def _nan_aware_equal(first: Any, second: Any) -> bool:
    """NaN == NaN 视为相等（数值表对拍必需）。"""
    if isinstance(first, dict) and isinstance(second, dict):
        return first.keys() == second.keys() and all(
            _nan_aware_equal(first[k], second[k]) for k in first
        )
    if isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
        return len(first) == len(second) and all(
            _nan_aware_equal(a, b) for a, b in zip(first, second)
        )
    if isna(first) and isna(second):
        return True
    return bool(first == second)


@unittest.skipIf(pd is None, "需要 pandas 才能做等价性对照")
class TableParityTests(unittest.TestCase):
    """Table 的每个语义都对拍 pandas.DataFrame。"""

    def _pair(self):
        return Table(ROWS), pd.DataFrame(ROWS)

    def assertSame(self, first: Any, second: Any, msg: str = "") -> None:
        self.assertTrue(
            _nan_aware_equal(first, second),
            msg=f"{msg}\n  Table : {first!r}\n  pandas: {second!r}",
        )

    def test_columns_and_shape_match(self) -> None:
        table, frame = self._pair()
        self.assertEqual(list(table.columns), list(frame.columns))
        self.assertEqual(table.shape, frame.shape)
        self.assertEqual(len(table), len(frame))

    def test_empty_matches(self) -> None:
        self.assertEqual(Table().empty, pd.DataFrame().empty)
        self.assertEqual(Table(ROWS).empty, pd.DataFrame(ROWS).empty)

    def test_column_access_matches(self) -> None:
        table, frame = self._pair()
        self.assertSame(list(table["scope"]), list(frame["scope"]))

    def test_boolean_mask_filter_matches(self) -> None:
        table, frame = self._pair()
        focus_t = table[table["scope"] == "spatial"]
        focus_p = frame[frame["scope"] == "spatial"]
        self.assertEqual(len(focus_t), len(focus_p))
        self.assertEqual(list(focus_t["field"]), list(focus_p["field"]))

    def test_combined_mask_matches(self) -> None:
        table, frame = self._pair()
        scope = "damage_gt_0.05"
        t = table[(table["scope"] == scope) & (table["field"] == "raw")]
        p = frame[(frame["scope"] == scope) & (frame["field"] == "raw")]
        self.assertEqual(len(t), len(p))
        self.assertEqual(float(t.iloc[0]["MeanRelativeError"]),
                         float(p.iloc[0]["MeanRelativeError"]))

    def test_iloc_row_access_matches(self) -> None:
        table, frame = self._pair()
        for i in range(len(ROWS)):
            self.assertSame(float(table.iloc[i]["MeanRelativeError"]),
                            float(frame.iloc[i]["MeanRelativeError"]))
            self.assertEqual(table.iloc[i]["scope"], frame.iloc[i]["scope"])

    def test_iloc_get_with_default_matches(self) -> None:
        table, frame = self._pair()
        self.assertSame(table.iloc[2].get("IoU", np.nan),
                        frame.iloc[2].get("IoU", np.nan))

    def test_iterrows_matches(self) -> None:
        table, frame = self._pair()
        t_scopes = [row["scope"] for _, row in table.iterrows()]
        p_scopes = [row["scope"] for _, row in frame.iterrows()]
        self.assertEqual(t_scopes, p_scopes)

    def test_insert_matches(self) -> None:
        table, frame = self._pair()
        table.insert(0, "level", "F")
        frame.insert(0, "level", "F")
        self.assertEqual(list(table.columns), list(frame.columns))
        self.assertEqual(list(table["level"]), list(frame["level"]))

    def test_pop_matches(self) -> None:
        table, frame = self._pair()
        t_col = table.pop("field")
        p_col = frame.pop("field")
        self.assertEqual(list(t_col), list(p_col))
        self.assertEqual(list(table.columns), list(frame.columns))

    def test_columns_setter_matches(self) -> None:
        table, frame = self._pair()
        new = ["s", "f", "mre", "p95", "iou"]
        table.columns = new
        frame.columns = new
        self.assertEqual(list(table.columns), list(frame.columns))
        self.assertEqual(float(table.iloc[0]["mre"]), float(frame.iloc[0]["mre"]))

    def test_to_dict_records_matches(self) -> None:
        table, frame = self._pair()
        self.assertSame(table.to_dict("records"), frame.to_dict("records"))

    def test_explicit_columns_subset_matches(self) -> None:
        table = Table(ROWS, columns=["scope", "field"])
        frame = pd.DataFrame(ROWS, columns=["scope", "field"])
        self.assertEqual(list(table.columns), list(frame.columns))

    def test_matrix_construction_matches(self) -> None:
        matrix = np.arange(6, dtype=np.float64).reshape(2, 3)
        table = Table(matrix, index=[10.0, 20.0], columns=["a", "b", "c"])
        frame = pd.DataFrame(matrix, index=[10.0, 20.0], columns=["a", "b", "c"])
        self.assertEqual(list(table.columns), list(frame.columns))
        self.assertEqual(table.index.tolist(), list(frame.index))
        self.assertEqual(table.to_numpy().tolist(), frame.to_numpy().tolist())

    def test_transpose_matches(self) -> None:
        table = Table([{"a": 1, "b": 2}], columns=["a", "b"])
        frame = pd.DataFrame([{"a": 1, "b": 2}], columns=["a", "b"])
        self.assertSame(table.T.to_dict("records"), frame.T.to_dict("records"))

    def test_dropna_axis1_how_all_matches(self) -> None:
        rows = [{"a": 1.0, "b": np.nan}, {"a": 2.0, "b": np.nan}]
        table = Table(rows).dropna(axis=1, how="all")
        frame = pd.DataFrame(rows).dropna(axis=1, how="all")
        self.assertEqual(list(table.columns), list(frame.columns))

    def test_index_name_default_matches(self) -> None:
        matrix = np.zeros((2, 2))
        table = Table(matrix, index=[1.0, 2.0], columns=["a", "b"])
        frame = pd.DataFrame(matrix, index=[1.0, 2.0], columns=["a", "b"])
        table.index.name = "y"
        frame.index.name = "y"
        self.assertEqual(table.index.name, frame.index.name)


class TableStandaloneTests(unittest.TestCase):
    """不依赖 pandas 的自身契约（[core] 最小安装下也要通过）。"""

    def test_isna_semantics(self) -> None:
        self.assertTrue(isna(None))
        self.assertTrue(isna(float("nan")))
        self.assertTrue(isna(np.float64("nan")))
        self.assertFalse(isna(0.0))
        self.assertFalse(isna(""))
        self.assertFalse(isna("nan"))

    def test_notna_is_inverse(self) -> None:
        for value in (None, float("nan"), 0.0, "x"):
            self.assertEqual(notna(value), not isna(value))

    def test_to_numeric_coerce(self) -> None:
        self.assertEqual(to_numeric("1.5"), 1.5)
        self.assertTrue(isna(to_numeric("abc")))
        self.assertEqual(to_numeric("abc", default=0.0), 0.0)

    def test_table_from_empty(self) -> None:
        table = Table()
        self.assertTrue(table.empty)
        self.assertEqual(len(table), 0)
        self.assertEqual(list(table.columns), [])

    def test_table_from_dict_of_columns(self) -> None:
        table = Table({"a": [1, 2], "b": [3, 4]})
        self.assertEqual(list(table.columns), ["a", "b"])
        self.assertEqual(len(table), 2)
        self.assertEqual(table.iloc[0]["a"], 1)

    def test_missing_column_raises(self) -> None:
        with self.assertRaises(KeyError):
            Table(ROWS)["nope"]

    def test_insert_beyond_length_fills_nan(self) -> None:
        table = Table(ROWS)
        table.insert(0, "level", ["F"])
        self.assertEqual(table.iloc[0]["level"], "F")
        self.assertTrue(isna(table.iloc[1]["level"]))

    def test_to_csv_roundtrip_without_index(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            Table(ROWS).to_csv(path, index=False, encoding="utf-8")
            back = read_csv(path, dtype=str)
            self.assertEqual(len(back), len(ROWS))
            self.assertEqual(back.iloc[0]["scope"], "damage_gt_0.05")

    def test_read_csv_tab_separated_skiprows(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.txt"
            path.write_text("header\n1\t2\t3\n4\t5\t6\n", encoding="gbk")
            table = read_csv(path, sep="\t", encoding="gbk", header=None, skiprows=1)
            self.assertEqual(len(table), 2)
            self.assertEqual(table.to_numpy(dtype=np.float32).shape, (2, 3))

    def test_read_csv_trailing_delimiter_column_drops_as_all_nan(self) -> None:
        """行尾多余分隔符产生的全空尾列按 pandas 语义转为 NaN 并可被丢弃。

        回归守卫：GBK 数据文件常见的行尾 \\t 曾让空字段保留为 ""，
        dropna(axis=1, how="all") 不丢弃该列，下游 to_numpy(float32) 崩溃。
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.txt"
            path.write_text("header\n1\t2\t\n3\t4\t\n", encoding="gbk")
            table = read_csv(path, sep="\t", encoding="gbk", header=None, skiprows=1)
            dropped = table.dropna(axis=1, how="all")
            self.assertEqual(len(dropped.columns), 2)
            np.testing.assert_allclose(
                dropped.to_numpy(dtype=np.float32), [[1.0, 2.0], [3.0, 4.0]]
            )

    def test_read_csv_dtype_str_empty_field_is_nan(self) -> None:
        """dtype=str 下空字段仍为 NaN（pandas 语义），非空字段保持字符串。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.csv"
            path.write_text("job_id,h\n00123,\n", encoding="utf-8")
            table = read_csv(path, dtype=str)
            self.assertEqual(table.iloc[0]["job_id"], "00123")  # 前导零保留
            self.assertTrue(isna(table.iloc[0]["h"]))

    def test_mask_logic_operators(self) -> None:
        table = Table(ROWS)
        mask = (table["scope"] == "spatial") | (table["field"] == "raw")
        self.assertEqual(list(mask), [False, True, True])
        self.assertEqual(list(~mask), [True, False, False])


if __name__ == "__main__":
    unittest.main()
