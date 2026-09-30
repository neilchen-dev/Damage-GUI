"""Narrow icon tool rail replacing the wide text sidebar."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QVBoxLayout, QWidget

from damage_gui.qt.i18n import Translator
from damage_gui.qt.icons import IconToolButton
from damage_gui.qt.theme import SM, XS

# key, translation key
RAIL_ITEMS = tuple((key, f"nav.{key}") for key in
                   ("prediction", "batch", "validation", "training", "models", "aim", "history", "settings"))


class ToolRail(QWidget):
    """56 px icon navigation; names appear as tooltips only."""

    navigation_requested = Signal(str)

    def __init__(self, translator: Translator, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("toolrail")
        self.setFixedWidth(56)
        self._buttons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, SM, 6, SM)
        layout.setSpacing(XS)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, text_key in RAIL_ITEMS:
            button = IconToolButton(key)
            button.setCheckable(True)
            button.setFixedSize(44, 44)
            button.setProperty("role", "rail")
            button.clicked.connect(lambda _=False, k=key: self.navigation_requested.emit(k))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[key] = (button, text_key)
        layout.addStretch()
        self.retranslate()

    def set_current(self, key):
        if key in self._buttons:
            self._buttons[key][0].setChecked(True)

    def retranslate(self):
        for button, text_key in self._buttons.values():
            button.setToolTip(self.translator.t(text_key))
            button.setAccessibleName(self.translator.t(text_key))
