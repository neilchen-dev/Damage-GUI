"""批量预测测试：CSV 解析校验、执行器（部分失败/取消/真值对照）、输出与追溯。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.batch.runner import run_batch
from damage_gui.batch.schema import OUTPUT_COLUMNS, parse_batch_csv
from damage_gui.errors import DataValidationError
from synthetic_data import make_service, make_synthetic_dataset


def write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8-sig")
    return path


class BatchSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse_valid_csv_with_optional_columns(self) -> None:
        csv_path = write_csv(
            self.tmp / "in.csv",
            "job_id,h,v,deg,level\n001,1,300,30,F\n002,2,350,40,F\n",
        )
        parsed = parse_batch_csv(csv_path, default_level="F")
        self.assertEqual(parsed.total, 2)
        self.assertEqual(len(parsed.invalid), 0)
        self.assertEqual(parsed.rows[0].job_id, "001")
        self.assertEqual(parsed.rows[1].level, "F")

    def test_parse_generates_job_id_and_default_level(self) -> None:
        csv_path = write_csv(self.tmp / "in.csv", "h,v,deg\n1,300,30\n")
        parsed = parse_batch_csv(csv_path, default_level="M")
        self.assertEqual(parsed.rows[0].job_id, "0001")
        self.assertEqual(parsed.rows[0].level, "M")

    def test_missing_required_column_rejects_file(self) -> None:
        csv_path = write_csv(self.tmp / "in.csv", "job_id,h,deg\n001,1,30\n")
        with self.assertRaisesRegex(DataValidationError, "缺少必需列"):
            parse_batch_csv(csv_path)

    def test_missing_file_rejects(self) -> None:
        with self.assertRaisesRegex(DataValidationError, "不存在"):
            parse_batch_csv(self.tmp / "nowhere.csv")

    def test_row_level_errors_become_invalid_rows(self) -> None:
        csv_path = write_csv(
            self.tmp / "in.csv",
            "job_id,h,v,deg,level\n"
            "001,1,300,30,F\n"      # 合法
            "002,999,300,30,F\n"    # h 超范围
            "003,abc,300,30,F\n"    # 非数字
            "004,1,,30,F\n",        # v 为空 → NaN
        )
        parsed = parse_batch_csv(csv_path)
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(len(parsed.invalid), 3)
        messages = " ".join(item.error for item in parsed.invalid)
        self.assertIn("超出合法范围", messages)

    def test_empty_csv_rejects(self) -> None:
        csv_path = write_csv(self.tmp / "in.csv", "h,v,deg\n")
        with self.assertRaisesRegex(DataValidationError, "没有数据行"):
            parse_batch_csv(csv_path)


class BatchRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp, cls.data_dir = make_synthetic_dataset()
        cls.service = make_service(cls.data_dir)
        cls.bundle = cls.service.train_bundle(
            "F", validation_mode="random", model_type="rbf"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def setUp(self) -> None:
        self._out_tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._out_tmp.name)

    def tearDown(self) -> None:
        self._out_tmp.cleanup()

    def _rows(self):
        from damage_gui.batch.schema import BatchRowInput

        return [
            # 精确命中数据集工况（h=2, v=200, deg=10 在合成数据集中）→ 应带真值对照指标
            BatchRowInput(job_id="hit", h=2.0, v=200.0, deg=10.0, level="F"),
            # 未命中真值的合法工况
            BatchRowInput(job_id="miss", h=2.0, v=120.0, deg=12.0, level="F"),
        ]

    def test_batch_success_with_output_csv_and_db(self) -> None:
        db_path = self.tmp / "trace.db"
        output = self.tmp / "result.csv"
        report = run_batch(
            self.bundle,
            self._rows(),
            data_manager=self.service.data_manager,
            output_path=output,
            db_path=db_path,
            input_source="in.csv",
        )
        self.assertEqual(report.total, 2)
        self.assertEqual(report.success_count, 2)
        self.assertEqual(report.failed_count, 0)
        self.assertFalse(report.cancelled)
        self.assertTrue(report.db_recorded)
        self.assertTrue(output.is_file())

        frame = pd.read_csv(output, encoding="utf-8-sig")
        self.assertEqual(list(frame.columns), list(OUTPUT_COLUMNS))
        hit = frame[frame["job_id"] == "hit"].iloc[0]
        self.assertEqual(hit["status"], "SUCCESS")
        self.assertFalse(pd.isna(hit["mean_relative_error"]))  # 命中真值
        self.assertFalse(pd.isna(hit["ood_level"]))
        miss = frame[frame["job_id"] == "miss"].iloc[0]
        self.assertTrue(pd.isna(miss["mean_relative_error"]))  # 无真值

        # SQLite 追溯：job + 逐行结果
        with _connect(db_path) as conn:
            job = conn.execute(
                "SELECT * FROM jobs WHERE kind = 'batch_prediction'"
            ).fetchone()
            self.assertIsNotNone(job)
            count = conn.execute(
                "SELECT COUNT(*) FROM prediction_results"
            ).fetchone()[0]
            self.assertEqual(count, 2)

    def test_single_row_failure_does_not_abort_batch(self) -> None:
        from damage_gui.batch.schema import BatchRowInput, InvalidBatchRow

        rows = self._rows() + [
            BatchRowInput(job_id="bad_level", h=1.0, v=150.0, deg=10.0, level="M"),
        ]
        invalid = [InvalidBatchRow(line_no=5, job_id="bad_row", error="h 超出合法范围")]
        report = run_batch(
            self.bundle, rows, invalid_rows=invalid,
            db_path=self.tmp / "trace2.db",
        )
        self.assertEqual(report.total, 4)
        self.assertEqual(report.success_count, 2)
        self.assertEqual(report.failed_count, 2)
        failed = {row.job_id: row for row in report.rows if row.status == "FAILED"}
        self.assertIn("与模型等级", failed["bad_level"].error_message or "")
        self.assertIn("输入校验失败", failed["bad_row"].error_message or "")

    def test_cancel_stops_processing_remaining_rows(self) -> None:
        report = run_batch(
            self.bundle, self._rows(),
            db_path=self.tmp / "trace3.db",
            cancel_check=lambda: True,
        )
        self.assertTrue(report.cancelled)
        self.assertEqual(report.success_count, 0)

    def test_db_failure_degrades_explicitly(self) -> None:
        """SQLite 故障：结果照常产出，db_recorded=False 且有 ERROR 日志。"""
        bad_db = self.tmp / "not_a_db"
        bad_db.mkdir()  # 目录冒充数据库文件 → 写入必败
        output = self.tmp / "result.csv"
        with self.assertLogs("damage_gui.storage", level="ERROR"):
            report = run_batch(
                self.bundle, self._rows(),
                output_path=output,
                db_path=bad_db,
            )
        self.assertEqual(report.success_count, 2)  # 计算不受影响
        self.assertFalse(report.db_recorded)      # 追溯失败显式可见
        self.assertTrue(output.is_file())          # 输出照常落盘


@contextmanager
def _connect(db_path: Path):
    """测试用连接：退出时真正关闭（Windows 下未关闭会锁住文件）。"""
    from damage_gui.storage.db import connect

    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()
