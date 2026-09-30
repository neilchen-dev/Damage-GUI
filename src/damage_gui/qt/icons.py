"""Small bundled outline icon set, tinted from the application palette."""
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QToolButton

from damage_gui.qt import theme

ICON_DIR = Path(__file__).with_name("icons")

def icon(name, color, size=20):
    svg = (ICON_DIR / f"{name}.svg").read_text().replace("#667284", color)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)

class IconToolButton(QToolButton):
    def __init__(self, name, *, dark=False, parent=None):
        super().__init__(parent)
        self.icon_name = name
        self.dark = dark
        self._hover = False
        self.setIconSize(QSize(20, 20))
        self.toggled.connect(self._refresh_icon)
        self._refresh_icon()

    def _refresh_icon(self, *_):
        t = theme.QtTheme()
        if self.dark:
            color = theme.VIEWPORT_ACCENT if self.isChecked() else (
                theme.VIEWPORT_TEXT if self._hover else theme.VIEWPORT_MUTED)
        else:
            color = t.primary if self.isChecked() else (t.text if self._hover else t.muted)
        self.setIcon(icon(self.icon_name, color))

    def enterEvent(self, event):
        self._hover = True
        self._refresh_icon()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._refresh_icon()
        super().leaveEvent(event)
