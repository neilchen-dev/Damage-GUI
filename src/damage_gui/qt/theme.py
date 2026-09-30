"""CAE workbench palette: light application shell around a dark scientific viewport."""
from dataclasses import dataclass
from pathlib import Path

from damage_gui.visualization.theme import DARK_SCIENTIFIC

# Shared spacing and type scale, in logical pixels.
XS, SM, MD, LG, XL = 4, 8, 12, 16, 24
APP_TITLE, WORKSPACE_TITLE, SECTION, BODY, METADATA = 13, 16, 11, 12, 11
INPUT_HEIGHT, PRIMARY_HEIGHT = 34, 36
RADIUS_SMALL, RADIUS = 3, 4
VIEWPORT_AXIS = DARK_SCIENTIFIC.label
PLOT_TICK = DARK_SCIENTIFIC.tick
PLOT_EDGE = DARK_SCIENTIFIC.edge
PLOT_TITLE = DARK_SCIENTIFIC.title
VIEWPORT_GRID = DARK_SCIENTIFIC.grid

# Dark scientific viewport surfaces (Matplotlib canvas adapts to these).
VIEWPORT_BG = DARK_SCIENTIFIC.background
VIEWPORT_BAR = "#1B2028"
VIEWPORT_BORDER = "#2A3039"
VIEWPORT_HOVER = "#242B36"
VIEWPORT_TEXT = "#D6DCE5"
VIEWPORT_MUTED = "#8E98A7"
VIEWPORT_ACCENT = "#8FB4E8"


@dataclass(frozen=True)
class QtTheme:
    bg: str = "#F5F6F8"
    panel_bg: str = "#FFFFFF"
    soft_bg: str = "#F2F4F7"
    border: str = "#E1E5EA"
    text: str = "#202632"
    muted: str = "#687385"
    faint: str = "#98A1AE"
    primary: str = "#3568B8"
    primary_dark: str = "#2E5A9E"
    accent_soft: str = "#EAF1FB"
    success: str = "#3D8B68"
    danger: str = "#C55252"
    busy: str = "#C28A2C"


def build_stylesheet(theme=None):
    t = theme or QtTheme()
    icons = Path(__file__).with_name("icons").as_posix()
    return f"""
    QWidget {{ color: {t.text}; font-size: 12px; }}
    QMainWindow {{ background: {t.bg}; }}
    QLabel {{ background: transparent; }}

    /* ---- Application shell (light) ---- */
    QWidget#appbar {{ background: {t.panel_bg}; border-bottom: 1px solid {t.border}; }}
    QWidget#toolrail {{ background: {t.soft_bg}; border-right: 1px solid {t.border}; }}
    QWidget#pageHeader {{ background: {t.panel_bg}; border-bottom: 1px solid {t.border}; }}
    QWidget#inspectorDock {{ background: {t.panel_bg}; border-left: 1px solid {t.border}; }}
    QWidget#activityPanel {{ background: {t.panel_bg}; border-top: 1px solid {t.border}; }}

    QLabel[role="app-name"] {{ font-size: 13px; font-weight: 600; }}
    QLabel[role="page-title"] {{ font-size: {WORKSPACE_TITLE}px; font-weight: 600; }}
    QLabel[role="section"] {{ color: {t.faint}; font-size: 10px; font-weight: 700; }}
    QLabel[role="field"], QLabel[role="secondary"],
    QLabel[role="metric-label"] {{ color: {t.muted}; font-size: 11px; }}
    QLabel[role="value"] {{ font-size: 12px; font-weight: 600; }}
    QLabel[role="status-info"],
    QLabel[role="status-neutral"] {{ color: {t.muted}; font-size: 11px; }}
    QLabel[role="status-success"],
    QLabel[role="status-ok"] {{ color: {t.success}; font-size: 11px; }}
    QLabel[role="status-error"] {{ color: {t.danger}; font-size: 11px; }}
    QLabel[role="status-running"] {{ color: {t.primary}; font-size: 11px; }}
    QLabel[role="status-busy"],
    QLabel[role="status-warning"] {{ color: {t.busy}; font-size: 11px; }}
    QFrame[role="divider"] {{ background: {t.border}; border: none; max-height: 1px; }}

    QMenuBar {{ background: transparent; }}
    QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {t.soft_bg}; }}
    QMenu {{ background: {t.panel_bg}; border: 1px solid {t.border}; padding: 4px; }}
    QMenu::item {{ padding: 5px 26px 5px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t.soft_bg}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 8px; }}

    QToolButton[role="rail"] {{
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        font-size: 17px; color: {t.muted};
    }}
    QToolButton[role="rail"]:hover {{ background: {t.soft_bg}; color: {t.text}; }}
    QToolButton[role="rail"]:checked {{
        background: {t.accent_soft}; color: {t.primary};
        border-left: 3px solid {t.primary};
    }}

    QPushButton, QToolButton {{
        background: transparent; border: 1px solid transparent;
        border-radius: 4px; padding: 3px 10px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {t.soft_bg}; }}
    QPushButton[role="primary"] {{ background: {t.primary}; color: white; padding: 5px 16px; }}
    QPushButton[role="primary"]:hover {{ background: {t.primary_dark}; }}
    QPushButton:disabled {{ color: {t.muted}; background: {t.soft_bg}; }}

    QToolButton[role="tab"] {{
        color: {t.muted}; font-size: 11px; padding: 3px 10px;
        border-bottom: 2px solid transparent; border-radius: 0;
    }}
    QToolButton[role="tab"]:hover {{ color: {t.text}; }}
    QToolButton[role="tab"]:checked {{ color: {t.text}; border-bottom-color: {t.primary}; }}
    QToolButton[role="collapse"] {{ color: {t.muted}; font-size: 10px; padding: 1px 5px; }}

    QDoubleSpinBox, QComboBox, QLineEdit {{
        background: {t.panel_bg}; border: 1px solid {t.border};
        border-radius: 4px; padding: 2px 8px; font-size: 12px;
    }}
    QDoubleSpinBox:hover, QComboBox:hover, QLineEdit:hover {{ border-color: #BCC5D1; }}
    QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{ border-color: {t.primary}; }}
    QDoubleSpinBox:disabled, QComboBox:disabled, QLineEdit:disabled {{ background: {t.soft_bg}; color: {t.faint}; }}
    QComboBox {{ padding-right: 28px; border-color: #D9DEE5; }}
    QComboBox::drop-down {{ width: 28px; border: none; }}
    QComboBox::down-arrow {{ image: url("{icons}/chevron-down.svg"); width: 16px; height: 16px; }}
    QComboBox QAbstractItemView {{ background: {t.panel_bg}; border: 1px solid {t.border}; outline: none; selection-background-color: {t.accent_soft}; selection-color: #234A84; }}
    QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 8px; }}
    QDoubleSpinBox, QLineEdit {{ border-color: #D9DEE5; }}
    QDoubleSpinBox {{ padding-right: 20px; }}
    QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; }}
    QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; }}
    QDoubleSpinBox::up-arrow {{ image: url("{icons}/chevron-up.svg"); width: 12px; height: 12px; }}
    QDoubleSpinBox::down-arrow {{ image: url("{icons}/chevron-down.svg"); width: 12px; height: 12px; }}
    QPushButton[role="primary"]:pressed {{ background: #274D88; }}
    QPushButton[role="primary"]:disabled {{ background: #E7EAF0; color: #9BA4B1; }}
    QPushButton[role="empty-action"] {{ background: {VIEWPORT_BAR}; color: {VIEWPORT_TEXT}; border: 1px solid {VIEWPORT_BORDER}; }}
    QPushButton[role="empty-action"]:hover {{ background: {VIEWPORT_HOVER}; border-color: {VIEWPORT_MUTED}; }}
    QStackedWidget#activityContent {{ background: {t.bg}; border-top: 1px solid {t.border}; }}
    QStackedWidget#activityContent QPlainTextEdit {{ background: {t.bg}; }}
    QLabel[role="model-id"] {{ font-size: 12px; }}
    QPlainTextEdit {{ background: {t.panel_bg}; border: none; padding: 8px; font-size: 11px; }}
    QSplitter::handle {{ background: {t.border}; height: 1px; }}

    QWidget#inspectorContent, QScrollArea#inspectorScroll {{ background: {t.panel_bg}; }}
    QScrollArea#detailDark, QWidget#detailContentDark {{ background: {VIEWPORT_BG}; }}
    QScrollArea#detailLight, QWidget#detailContentLight {{ background: {t.panel_bg}; }}
    QWidget#detailContentDark QLabel[role="section"] {{ color: {VIEWPORT_MUTED}; font-size: {SECTION}px; font-weight: 600; }}
    QWidget#detailContentDark QLabel[role="metric-label"] {{ color: {VIEWPORT_MUTED}; }}
    QWidget#detailContentDark QLabel[role="value"] {{ color: {VIEWPORT_TEXT}; font-weight: 500; }}
    QWidget#detailContentDark QToolButton {{ color: {VIEWPORT_MUTED}; }}
    QTableView {{ font-size: 11px; }}
    QTableView::item:hover {{ background: {t.accent_soft}; }}
    QTableView#workflowTableDark::item:hover {{ background: {VIEWPORT_HOVER}; }}
    /* ---- Scientific viewport (dark) ---- */
    QWidget#viewport, QWidget#viewportEmpty, QStackedWidget#viewportStack {{ background: {VIEWPORT_BG}; }}
    QWidget#viewportBar {{
        background: {VIEWPORT_BAR}; border-bottom: 1px solid {VIEWPORT_BORDER};
    }}
    QToolButton[role="view-tool"] {{
        background: transparent; border: 1px solid transparent; border-radius: 4px;
        color: {VIEWPORT_MUTED}; font-size: 11px; padding: 3px 10px;
    }}
    QToolButton[role="view-tool"]:hover {{ background: {VIEWPORT_HOVER}; color: {VIEWPORT_TEXT}; }}
    QToolButton[role="view-tool"]:checked {{
        background: #243246; color: {VIEWPORT_ACCENT}; font-weight: 600;
    }}
    QToolButton[role="view-tool"]:disabled {{ color: #4A5261; }}
    QLabel[role="probe-readout"] {{ color: {VIEWPORT_MUTED}; font-size: 11px; }}
    QLabel[role="empty-title"] {{ color: {VIEWPORT_TEXT}; font-size: 17px; font-weight: 600; }}
    QLabel[role="empty-body"] {{ color: {VIEWPORT_MUTED}; font-size: 12px; }}
    QWidget#trainingInspectorContent, QScrollArea#trainingInspectorScroll {{ background: {t.panel_bg}; }}
    QWidget#batchWorkspace {{ background: {VIEWPORT_BG}; }}
    QWidget#batchWorkspace QLabel {{ color: {VIEWPORT_TEXT}; }}
    QWidget#batchWorkspace QLabel[role="secondary"] {{ color: {VIEWPORT_MUTED}; }}
    QWidget#batchWorkspace QLabel[role="status-success"] {{ color: {t.success}; }}
    QWidget#batchWorkspace QLabel[role="status-running"] {{ color: {VIEWPORT_ACCENT}; }}
    QWidget#batchWorkspace QLabel[role="status-error"] {{ color: {t.danger}; }}
    QWidget#batchWorkspace QLabel[role="status-warning"] {{ color: {t.busy}; }}
    QTableView {{ border: none; background: {t.panel_bg}; selection-background-color: #DEE8F6; selection-color: #172334; }}
    QTableView#workflowTableDark {{ background: {VIEWPORT_BG}; color: {VIEWPORT_TEXT}; selection-background-color: #243246; selection-color: {VIEWPORT_TEXT}; }}
    QHeaderView::section {{ border: none; border-bottom: 1px solid {t.border}; background: {t.bg}; padding: 5px; font-size: 11px; }}
    QTableView#workflowTableDark QHeaderView::section {{ background: {VIEWPORT_BAR}; color: {VIEWPORT_MUTED}; border-bottom: 1px solid {VIEWPORT_BORDER}; }}
    QProgressBar {{ border: none; background: #293240; }}
    QProgressBar::chunk {{ background: {VIEWPORT_ACCENT}; }}
    QWidget#batchWorkspace QTabWidget::pane {{ border: none; background: {VIEWPORT_BG}; }}
    QWidget#batchWorkspace QTabBar::tab {{ background: {VIEWPORT_BAR}; color: {VIEWPORT_MUTED}; padding: 6px 14px; border-bottom: 1px solid {VIEWPORT_BORDER}; }}
    QWidget#batchWorkspace QTabBar::tab:selected {{ color: {VIEWPORT_ACCENT}; border-bottom: 2px solid {VIEWPORT_ACCENT}; }}
    QPlainTextEdit#validationSummary {{ background: {VIEWPORT_BG}; color: {VIEWPORT_TEXT}; border: none; font-size: 12px; }}
    """
