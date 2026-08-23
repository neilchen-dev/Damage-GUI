"""统一错误体系与日志初始化测试。"""
from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.errors import (
    DamageGuiError,
    DataValidationError,
    ModelLoadError,
    OperationCancelled,
    PredictionError,
    TaskStateError,
)
from damage_gui.logging_setup import LOG_FILE_NAME, setup_logging
from damage_gui.model.bundle import TrainingCancelled


class ErrorHierarchyTests(unittest.TestCase):
    def test_all_errors_share_damage_gui_base(self) -> None:
        for error_cls in (
            DataValidationError, ModelLoadError, PredictionError,
            OperationCancelled, TaskStateError,
        ):
            self.assertTrue(issubclass(error_cls, DamageGuiError))

    def test_training_cancelled_is_operation_cancelled(self) -> None:
        # 训练取消沿用既有异常类型名，但已挂入统一错误体系
        self.assertTrue(issubclass(TrainingCancelled, OperationCancelled))
        self.assertTrue(issubclass(TrainingCancelled, DamageGuiError))


class LoggingSetupTests(unittest.TestCase):
    @staticmethod
    def _reset_logging() -> None:
        """关闭并移除已有 handler、复位幂等标记（顺序无关的测试前提）。

        其他测试（如 CLI）可能已调用过 setup_logging()，本类必须能在
        任意执行顺序下验证"首次初始化"行为。
        """
        import damage_gui.logging_setup as logging_setup

        logger = logging.getLogger("damage_gui")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        logging_setup._configured = False

    def test_01_setup_logging_writes_rotating_file(self) -> None:
        import damage_gui.logging_setup as logging_setup

        self._reset_logging()
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            logger = setup_logging(log_dir=log_dir)
            handler_count = len(logger.handlers)
            self.assertGreaterEqual(handler_count, 2)  # 控制台 + 文件

            logger.info("日志初始化验证消息")
            for handler in logger.handlers:
                handler.flush()
            log_file = log_dir / LOG_FILE_NAME
            self.assertTrue(log_file.is_file())
            self.assertIn("日志初始化验证消息", log_file.read_text(encoding="utf-8"))

            # 清理：关闭文件句柄（Windows 会锁住临时目录），并复位幂等标记
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
            logging_setup._configured = False

    def test_02_setup_logging_is_idempotent(self) -> None:
        self._reset_logging()
        logger = setup_logging()
        handlers_before = len(logger.handlers)
        again = setup_logging()
        self.assertIs(logger, again)
        self.assertEqual(len(again.handlers), handlers_before)
        self.assertFalse(logger.propagate)


if __name__ == "__main__":
    unittest.main()
