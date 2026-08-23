"""任务状态机与 TaskManager 测试：状态转移、互斥、取消、失败与事件流。"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from damage_gui.errors import OperationCancelled, TaskStateError
from damage_gui.tasks import Task, TaskManager, TaskStatus


def wait_until(condition, timeout: float = 5.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


class TaskStateMachineTests(unittest.TestCase):
    def test_happy_path_transitions(self) -> None:
        task = Task(kind="training")
        self.assertEqual(task.status, TaskStatus.PENDING)
        task._transition(TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertIsNotNone(task.started_at)
        task._transition(TaskStatus.SUCCESS)
        self.assertEqual(task.status, TaskStatus.SUCCESS)
        self.assertIsNotNone(task.finished_at)

    def test_terminal_states_reject_any_transition(self) -> None:
        for terminal in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task = Task(kind="training")
            task._transition(TaskStatus.RUNNING)
            task._transition(terminal)
            with self.assertRaises(TaskStateError):
                task._transition(TaskStatus.RUNNING)

    def test_illegal_transition_raises(self) -> None:
        task = Task(kind="training")
        with self.assertRaises(TaskStateError):
            task._transition(TaskStatus.SUCCESS)  # PENDING 不能直接到 SUCCESS
        task._transition(TaskStatus.RUNNING)
        with self.assertRaises(TaskStateError):
            task._transition(TaskStatus.PENDING)  # RUNNING 不能回到 PENDING


class TaskManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = TaskManager()

    def _drain_until_finished(self, kind: str) -> list:
        events: list = []
        finished = threading.Event()

        def drain() -> None:
            while not finished.is_set():
                events.extend(self.manager.poll())
                last = [e for e in events if e.type == "finished" and e.kind == kind]
                if last:
                    finished.set()
                    return
                time.sleep(0.01)

        poller = threading.Thread(target=drain, daemon=True)
        poller.start()
        self.assertTrue(
            finished.wait(timeout=5.0), "等待任务 finished 事件超时"
        )
        events.extend(self.manager.poll())
        return events

    def test_submit_success_flow_with_progress(self) -> None:
        def work(ctx) -> int:
            ctx.report_progress(1, 2, "阶段一")
            ctx.report_progress(2, 2, "阶段二")
            return 42

        self.manager.submit("training", work)
        events = self._drain_until_finished("training")
        types = [event.type for event in events]
        self.assertIn("started", types)
        self.assertGreaterEqual(types.count("progress"), 2)
        finished = [e for e in events if e.type == "finished"][0]
        self.assertEqual(finished.status, TaskStatus.SUCCESS)
        self.assertEqual(finished.result, 42)
        self.assertIsNotNone(finished.duration_ms)
        self.assertFalse(self.manager.is_busy())

    def test_duplicate_submit_is_rejected(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def work(ctx) -> None:
            started.set()
            release.wait(timeout=5.0)

        self.manager.submit("training", work)
        self.assertTrue(started.wait(timeout=5.0))
        with self.assertRaises(TaskStateError):
            self.manager.submit("training", work)
        release.set()
        self._drain_until_finished("training")

    def test_worker_exception_marks_failed(self) -> None:
        def work(ctx) -> None:
            ctx.report_progress(0, 1, "准备")
            raise ValueError("训练数据异常")

        self.manager.submit("training", work)
        events = self._drain_until_finished("training")
        finished = [e for e in events if e.type == "finished"][0]
        self.assertEqual(finished.status, TaskStatus.FAILED)
        self.assertIn("训练数据异常", finished.error_summary or "")
        self.assertIsNone(finished.result)

    def test_operation_cancelled_marks_cancelled(self) -> None:
        def work(ctx) -> None:
            raise OperationCancelled("用户取消训练")

        self.manager.submit("training", work)
        events = self._drain_until_finished("training")
        finished = [e for e in events if e.type == "finished"][0]
        self.assertEqual(finished.status, TaskStatus.CANCELLED)

    def test_cooperative_cancel_via_check(self) -> None:
        def work(ctx) -> str:
            while not ctx.cancel_check():
                time.sleep(0.005)
            raise OperationCancelled("用户取消训练")

        self.manager.submit("training", work)
        self.assertTrue(wait_until(lambda: self.manager.is_busy()))
        self.assertTrue(self.manager.cancel("training"))
        events = self._drain_until_finished("training")
        finished = [e for e in events if e.type == "finished"][0]
        self.assertEqual(finished.status, TaskStatus.CANCELLED)
        # 已结束的任务再取消 → False
        self.assertFalse(self.manager.cancel("training"))

    def test_cancel_returns_false_without_active_task(self) -> None:
        self.assertFalse(self.manager.cancel("training"))

    def test_shutdown_joins_active_threads(self) -> None:
        def work(ctx) -> None:
            while not ctx.cancel_check():
                time.sleep(0.005)

        self.manager.submit("training", work)
        self.assertTrue(wait_until(lambda: self.manager.is_busy()))
        self.manager.shutdown(timeout=3.0)
        task = self.manager.get("training")
        assert task is not None
        self.assertEqual(task.status, TaskStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
