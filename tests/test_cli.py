"""CLI 测试：info / predict / batch 三个子命令的返回码与产物。"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from damage_gui.cli import main
from damage_gui.model.registry import save_model
from synthetic_data import make_service, make_synthetic_dataset


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_data, cls.data_dir = make_synthetic_dataset()
        service = make_service(cls.data_dir)
        cls.bundle = service.train_bundle(
            "F", validation_mode="random", model_type="rbf"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp_data.cleanup()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.model_path = self.tmp / "model.joblib"
        save_model(self.bundle, self.model_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_info_prints_metadata(self) -> None:
        code, output, _ = self._run(["info", "--model", str(self.model_path)])
        self.assertEqual(code, 0)
        self.assertIn("毁伤等级: F", output)
        self.assertIn("模型 ID:", output)
        self.assertIn("软件版本", output)  # 三版本号行
        self.assertIn("训练数据指纹", output)

    def test_info_rejects_missing_model(self) -> None:
        code, _, _ = self._run(["info", "--model", str(self.tmp / "nope.joblib")])
        self.assertEqual(code, 2)

    def test_predict_exports_csv(self) -> None:
        export = self.tmp / "pred.csv"
        code, output, _ = self._run([
            "predict", "--model", str(self.model_path),
            "--h", "2", "--v", "200", "--deg", "10",
            "--export", str(export),
        ])
        self.assertEqual(code, 0)
        self.assertIn("预测完成", output)
        self.assertIn("模型可信度", output)
        self.assertTrue(export.is_file())

    def test_predict_rejects_out_of_range(self) -> None:
        code, _, stderr = self._run([
            "predict", "--model", str(self.model_path),
            "--h", "9999", "--v", "200", "--deg", "10",
        ])
        self.assertEqual(code, 2)
        self.assertIn("超出合法范围", stderr)

    def test_batch_reports_and_records(self) -> None:
        input_csv = self.tmp / "in.csv"
        input_csv.write_text(
            "job_id,h,v,deg,level\n001,2,200,10,F\n002,2,120,12,F\n",
            encoding="utf-8-sig",
        )
        output = self.tmp / "out.csv"
        db = self.tmp / "trace.db"
        code, output_text, _ = self._run([
            "batch", "--model", str(self.model_path),
            "--input", str(input_csv), "--output", str(output),
            "--db", str(db), "--data-dir", str(self.data_dir),
        ])
        self.assertEqual(code, 0)
        self.assertIn("成功 2/2", output_text)
        self.assertTrue(output.is_file())
        self.assertTrue(db.is_file())

    def test_batch_exit_code_marks_row_failures(self) -> None:
        input_csv = self.tmp / "in.csv"
        input_csv.write_text(
            "job_id,h,v,deg,level\n001,2,200,10,F\n002,1,150,15,M\n",
            encoding="utf-8-sig",
        )
        output = self.tmp / "out.csv"
        code, _, _ = self._run([
            "batch", "--model", str(self.model_path),
            "--input", str(input_csv), "--output", str(output),
            "--db", str(self.tmp / "t2.db"),
        ])
        self.assertEqual(code, 1)  # 有失败行 → 1
        self.assertTrue(output.is_file())

    def test_batch_rejects_bad_csv(self) -> None:
        input_csv = self.tmp / "bad.csv"
        input_csv.write_text("foo,bar\n1,2\n", encoding="utf-8-sig")
        code, _, _ = self._run([
            "batch", "--model", str(self.model_path),
            "--input", str(input_csv), "--output", str(self.tmp / "o.csv"),
        ])
        self.assertEqual(code, 2)

    def test_scripts_wrapper_forwards_to_cli(self) -> None:
        scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
        sys.path.insert(0, scripts_dir)
        try:
            import batch_predict
            from damage_gui import cli

            # 脚本入口与 CLI 共享同一 main 实现（薄封装，不重复业务逻辑）
            self.assertIs(batch_predict.main, cli.main)
        finally:
            sys.path.remove(scripts_dir)


if __name__ == "__main__":
    unittest.main()
