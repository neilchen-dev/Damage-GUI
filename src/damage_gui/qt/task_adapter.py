"""Bridge :class:`damage_gui.tasks.TaskManager` into the Qt event loop.

The existing manager uses a daemon thread + ``queue.Queue`` of
:class:`TaskEvent` snapshots.  Rather than rewrite it with ``QThread`` we
poll on a ``QTimer`` every ~80 ms and forward events as Qt signals.
This preserves the task lifecycle semantics (PENDING/RUNNING/SUCCESS/FAILED/
CANCELLED) and keeps Tk and Qt on the same underlying execution engine.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from damage_gui.tasks import TaskEvent, TaskManager, TaskStatus


class TaskAdapter(QObject):
    """Qt signal front for :class:`TaskManager`."""

    event_received = Signal(object)
    status_changed = Signal(str, str)

    def __init__(self, manager: TaskManager | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager or TaskManager()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._poll_interval_ms = 80
        self._submitted = {}

    @property
    def manager(self) -> TaskManager:
        return self._manager

    def start(self) -> None:
        self._timer.start(self._poll_interval_ms)

    def stop(self) -> None:
        self._timer.stop()
        self._manager.shutdown()

    def submit(self, kind: str, work):
        task = self._manager.submit(kind, work)
        self._submitted[kind] = task
        if not self._timer.isActive():
            self.start()
        if kind == 'prediction' or kind.startswith('prediction_finalize_'):
            self._timer.start(16)
        self.status_changed.emit(kind, task.status.value)
        return task

    def cancel(self, kind: str) -> bool:
        cancelled = self._manager.cancel(kind)
        if cancelled:
            self.status_changed.emit(kind, self._manager.get(kind).status.value)
        return cancelled

    def is_busy(self, kind: str | None = None) -> bool:
        return self._manager.is_busy(kind)

    def _poll(self) -> None:
        events: list[TaskEvent] = self._manager.poll()
        finished = {event.kind for event in events if event.type == 'finished'}
        for kind, task in list(self._submitted.items()):
            if task.status == TaskStatus.CANCELLED and task.started_at is None and kind not in finished:
                events.append(TaskEvent(kind=kind, type='finished', status=task.status,
                                        error_summary=task.error_summary, duration_ms=task.duration_ms))
                finished.add(kind)
        for kind in finished:
            self._submitted.pop(kind, None)
        latest = {event.kind: event for event in events if event.type == 'progress'}
        for event in events:
            if event.type == 'progress' and event is not latest[event.kind]:
                continue
            self.event_received.emit(event)
            self.status_changed.emit(event.kind, event.status.value)
        if not self._manager.is_busy() and not self._submitted:
            self._timer.stop()


__all__ = ["TaskAdapter"]
