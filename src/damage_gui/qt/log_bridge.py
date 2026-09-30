"""Forward existing damage_gui log records to Qt through queued signals."""
import logging

from PySide6.QtCore import QObject, Qt, Signal


class LogSignals(QObject):
    message = Signal(str)

class QtLogHandler(logging.Handler):
    def __init__(self, target):
        super().__init__()
        self.signals = LogSignals(target)
        self.signals.message.connect(target.append_log, Qt.QueuedConnection)
        self.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%H:%M:%S'))

    def emit(self, record):
        try:
            self.signals.message.emit(self.format(record))
        except RuntimeError:
            pass
