"""后台任务状态机与任务管理器。

GUI 只与 TaskManager 交互（提交 / 取消 / 轮询事件），不直接持有线程
对象；Tkinter UI 更新仍由 GUI 在主线程完成。取消为协作式：worker
通过 cancel_check 感知后在安全点抛出 OperationCancelled 子类。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from damage_gui.errors import OperationCancelled, TaskStateError

logger = logging.getLogger("damage_gui.tasks")

WorkFunction = Callable[["WorkContext"], Any]


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# 明确的状态转移表：终态不可再转移，非法转移抛 TaskStateError
_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.SUCCESS: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}

_ACTIVE_STATUSES = (TaskStatus.PENDING, TaskStatus.RUNNING)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class WorkContext:
    """传给 worker 的执行上下文：进度上报 + 协作式取消检查。"""

    report_progress: Callable[[int, int, str], None]
    cancel_check: Callable[[], bool]


@dataclass
class Task:
    """单个后台任务的可观测状态（含时间戳与耗时）。"""

    kind: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    progress_done: int = 0
    progress_total: int = 0
    stage: str = ""
    error_summary: str | None = None
    result: Any = None
    cancel_requested: bool = False

    def _transition(self, new_status: TaskStatus) -> None:
        if new_status not in _ALLOWED_TRANSITIONS[self.status]:
            raise TaskStateError(
                f"任务 {self.kind} 不允许从 {self.status.value} "
                f"转移到 {new_status.value}"
            )
        if new_status == TaskStatus.RUNNING:
            self.started_at = _now_iso()
        if new_status in (
            TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED,
        ):
            self.finished_at = _now_iso()
        self.status = new_status


@dataclass(frozen=True)
class TaskEvent:
    """投递给 GUI 主线程的任务事件（不可变快照）。"""

    kind: str
    type: str  # "started" | "progress" | "finished"
    status: TaskStatus
    done: int = 0
    total: int = 0
    stage: str = ""
    result: Any = None
    error_summary: str | None = None
    duration_ms: int | None = None


class TaskManager:
    """同 kind 任务互斥运行；事件经队列投递，由主线程 poll 消费。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._events: queue.Queue[TaskEvent] = queue.Queue()

    # ---------- 提交与控制 ----------

    def submit(self, kind: str, work: WorkFunction) -> Task:
        """提交后台任务；同 kind 任务运行中时拒绝重复启动。"""
        with self._lock:
            current = self._tasks.get(kind)
            if current is not None and current.status in _ACTIVE_STATUSES:
                raise TaskStateError(f"任务 {kind} 正在进行中，禁止重复启动")
            task = Task(kind=kind)
            self._tasks[kind] = task
        thread = threading.Thread(
            target=self._run, args=(task, work),
            daemon=True, name=f"damage-gui-task-{kind}",
        )
        with self._lock:
            self._threads[kind] = thread
        thread.start()
        return task

    def cancel(self, kind: str) -> bool:
        """请求取消（协作式）；任务未在运行则返回 False。"""
        with self._lock:
            task = self._tasks.get(kind)
            if task is None or task.status not in _ACTIVE_STATUSES:
                return False
            task.cancel_requested = True
        return True

    def poll(self) -> list[TaskEvent]:
        """非阻塞取走当前全部事件（GUI 在 after 轮询中调用）。"""
        events: list[TaskEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def get(self, kind: str) -> Task | None:
        with self._lock:
            return self._tasks.get(kind)

    def is_busy(self, kind: str | None = None) -> bool:
        with self._lock:
            kinds = [kind] if kind is not None else list(self._tasks)
            return any(
                self._tasks[name].status in _ACTIVE_STATUSES for name in kinds
            )

    def shutdown(self, timeout: float = 2.0) -> None:
        """窗口关闭前安全终止：请求取消全部活动任务并限时 join。"""
        with self._lock:
            tasks = [t for t in self._tasks.values() if t.status in _ACTIVE_STATUSES]
            for task in tasks:
                task.cancel_requested = True
            threads = list(self._threads.values())
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))

    # ---------- worker 侧 ----------

    def _run(self, task: Task, work: WorkFunction) -> None:
        started = time.perf_counter()
        try:
            with self._lock:
                if task.cancel_requested:
                    task._transition(TaskStatus.CANCELLED)
                    task.error_summary = "用户在任务启动前取消"
                    return
                task._transition(TaskStatus.RUNNING)
        except TaskStateError:  # 理论上不可达，防御性兜底
            logger.exception("任务 %s 状态异常", task.kind)
            return
        self._emit(task, "started")

        context = WorkContext(
            report_progress=lambda done, total, stage: self._report(
                task, done, total, stage
            ),
            cancel_check=lambda: task.cancel_requested,
        )
        try:
            result = work(context)
        except OperationCancelled as exc:
            self._finish(task, TaskStatus.CANCELLED, started,
                         error_summary=str(exc) or "用户取消任务")
            return
        except Exception as exc:  # noqa: BLE001 —— 线程边界统一上报并落日志
            logger.exception("任务 %s 执行失败", task.kind)
            self._finish(task, TaskStatus.FAILED, started,
                         error_summary=str(exc)[:500])
            return
        if task.cancel_requested:
            # worker 在取消请求后正常返回（如批量预测保留已完成行）：
            # 任务按 CANCELLED 收尾，但 result 保留供 GUI 展示部分结果
            self._finish(task, TaskStatus.CANCELLED, started, result=result,
                         error_summary="任务在取消请求后结束")
        else:
            self._finish(task, TaskStatus.SUCCESS, started, result=result)

    def _report(self, task: Task, done: int, total: int, stage: str) -> None:
        with self._lock:
            task.progress_done = done
            task.progress_total = total
            task.stage = stage
            snapshot = TaskEvent(
                kind=task.kind, type="progress", status=task.status,
                done=done, total=total, stage=stage,
            )
        self._events.put(snapshot)

    def _finish(
        self,
        task: Task,
        status: TaskStatus,
        started: float,
        result: Any = None,
        error_summary: str | None = None,
    ) -> None:
        with self._lock:
            task._transition(status)
            task.result = result
            task.error_summary = error_summary
            task.duration_ms = int((time.perf_counter() - started) * 1000)
            snapshot = TaskEvent(
                kind=task.kind, type="finished", status=task.status,
                done=task.progress_done, total=task.progress_total,
                stage=task.stage, result=task.result,
                error_summary=task.error_summary,
                duration_ms=task.duration_ms,
            )
        self._events.put(snapshot)

    def _emit(self, task: Task, event_type: str) -> None:
        with self._lock:
            snapshot = TaskEvent(
                kind=task.kind, type=event_type, status=task.status,
                done=task.progress_done, total=task.progress_total,
                stage=task.stage,
            )
        self._events.put(snapshot)
