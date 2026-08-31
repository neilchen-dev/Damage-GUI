"""Phase 1 service-boundary tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from damage_gui.config import Config
from damage_gui.data.loader import read_damage_matrix
from damage_gui.data.preprocessing import evaluation_fields
from damage_gui.errors import DataValidationError
from damage_gui.evaluation.metrics import metric_row
from damage_gui.optimization.aim import optimize_aim
from damage_gui.services.aim_service import AimService
from damage_gui.services.batch_service import BatchService
from damage_gui.services.conditions import validate_condition
from damage_gui.services.export_service import (
    export_figure_png,
    export_matrix_csv,
    matrix_to_frame,
)
from damage_gui.services.prediction_service import PredictionService
from damage_gui.services.training_service import TrainingService
from synthetic_data import make_service, make_synthetic_dataset


@contextmanager
def connect_and_close(path: Path):
    from damage_gui.storage.db import connect

    connection = connect(path)
    try:
        yield connection
    finally:
        connection.close()


class Phase1PureServiceTests(unittest.TestCase):
    def test_condition_validator_uses_domain_error_and_limits(self) -> None:
        self.assertEqual(validate_condition(h=0.0, v=1000.0, deg=90.0).deg, 90.0)
        with self.assertRaisesRegex(DataValidationError, "h=500.1 超出合法范围"):
            validate_condition(h=500.1, v=100.0, deg=10.0)

    def test_export_matrix_preserves_coordinate_dataframe(self) -> None:
        config = Config(coord_min=-1.0, coord_max=1.0, target_shape=(2, 3))
        matrix = np.arange(6, dtype=np.float32).reshape(2, 3)
        expected = matrix_to_frame(matrix, config)
        with tempfile.TemporaryDirectory() as directory:
            path = export_matrix_csv(matrix, Path(directory) / "matrix.csv", config)
            actual = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
        self.assertEqual(actual.index.name, expected.index.name)
        np.testing.assert_allclose(actual.index.to_numpy(), expected.index.to_numpy())
        np.testing.assert_allclose(
            actual.columns.astype(float).to_numpy(), expected.columns.to_numpy()
        )
        np.testing.assert_allclose(actual.to_numpy(), expected.to_numpy())

    def test_export_figure_does_not_need_gui(self) -> None:
        figure = Figure(figsize=(1, 1))
        figure.add_subplot(111).plot([0, 1], [0, 1])
        with tempfile.TemporaryDirectory() as directory:
            path = export_figure_png(figure, Path(directory) / "figure.png", dpi=80)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)

    def test_aim_service_matches_scientific_core(self) -> None:
        matrix = np.zeros((9, 9), dtype=np.float64)
        matrix[4, 5] = 1.0
        axis = np.linspace(-4.0, 4.0, 9)
        expected = optimize_aim(
            matrix,
            axis,
            axis,
            spread_mode="REP_DEP",
            rep=2.0,
            dep=3.0,
            rho=0.2,
            theta_deg=15.0,
        )
        actual = AimService().optimize(
            matrix,
            axis,
            axis,
            spread_mode="REP_DEP",
            rep="2.0",
            dep="3.0",
            rho="0.2",
            theta_deg="15.0",
        )
        np.testing.assert_allclose(actual.value_field, expected.value_field)
        np.testing.assert_allclose(actual.kernel, expected.kernel)
        self.assertEqual(actual.best_row, expected.best_row)
        self.assertEqual(actual.best_col, expected.best_col)
        self.assertAlmostEqual(actual.rho, expected.rho)
        self.assertIs(actual.optimization, actual.result)

    def test_batch_service_delegates_shared_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            path.write_text("h,v,deg\n1,300,30\n", encoding="utf-8-sig")
            parsed = BatchService().parse_csv(path, default_level="M")
        self.assertEqual(parsed.rows[0].level, "M")
        self.assertEqual(parsed.rows[0].job_id, "0001")


class Phase1ModelServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._dataset_tmp, cls.data_dir = make_synthetic_dataset()
        cls.model_service = make_service(cls.data_dir)
        cls.bundle = cls.model_service.train_bundle(
            "F", validation_mode="random", model_type="rbf"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._dataset_tmp.cleanup()

    def test_prediction_result_matches_prediction_truth_and_ood(self) -> None:
        condition = self.bundle.train_conditions[0]
        domain_condition = validate_condition(**condition)
        result = PredictionService(
            self.model_service.data_manager,
            model_service=self.model_service,
        ).predict(self.bundle, domain_condition)

        expected_prediction = self.bundle.model.predict_matrix(domain_condition)
        np.testing.assert_allclose(result.prediction, expected_prediction)
        self.assertIsNotNone(result.truth)
        self.assertIsNotNone(result.ood_report)
        self.assertEqual(result.confidence, result.ood_report.level_label)
        self.assertEqual(result.advice.has_truth, True)
        self.assertEqual(result.advice.has_focus_damage, True)

        record = self.model_service.data_manager.find_record(
            self.bundle.level, domain_condition
        )
        assert record is not None
        truth = read_damage_matrix(record.path, self.bundle.resolved_config())
        eval_true, eval_pred = evaluation_fields(
            truth, expected_prediction, self.bundle.resolved_config()
        )
        mask = eval_true.ravel() > self.bundle.resolved_config().relative_error_threshold
        expected_metrics = metric_row(
            "damage_gt_0.05",
            eval_true.ravel()[mask],
            eval_pred.ravel()[mask],
            self.bundle.resolved_config().relative_error_threshold,
            self.bundle.resolved_config(),
        )
        self.assertAlmostEqual(
            result.truth_comparison_metrics["MeanRelativeError"],
            expected_metrics["MeanRelativeError"],
        )
        self.assertAlmostEqual(
            result.truth_comparison_metrics["P95HybridError"],
            expected_metrics["P95HybridError"],
        )

    def test_training_service_persists_reports_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            model_service = Mock()
            model_service.train_bundle.return_value = self.bundle
            result = TrainingService(
                model_service,
                db_path=output_dir / "trace.db",
                report_dir=output_dir,
            ).train("F", validation_mode="random", model_type="rbf")

            model_service.train_bundle.assert_called_once()
            self.assertEqual(result.bundle, self.bundle)
            self.assertTrue(result.accuracy_report_path.is_file())
            self.assertTrue(result.condition_report_path.is_file())
            self.assertTrue(result.db_recorded)
            with connect_and_close(output_dir / "trace.db") as conn:
                job = conn.execute(
                    "SELECT kind, status FROM jobs WHERE kind = 'training'"
                ).fetchone()
            self.assertEqual(tuple(job), ("training", "SUCCESS"))


if __name__ == "__main__":
    unittest.main()
