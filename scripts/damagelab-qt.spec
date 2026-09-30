# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the DamageLab Qt desktop release (Phase 2.5).

Build from the repository root:

    pyinstaller scripts/damagelab-qt.spec --noconfirm --clean

Artifacts (onedir, windowed):

    dist/DamageLab-<version>-<platform>/        Linux / Windows
    dist/DamageLab-<version>-<platform>.app/    macOS bundle (renamed by
                                                scripts/build_qt_release.sh)

Notes:
- entry point is the **Qt** app (damage_gui.qt.app), NOT the legacy
  Tkinter desktop; legacy stays available via `pip install` entry points.
- bundled data: Qt SVG icon set, app icons, matplotlib resources are
  collected by the built-in hook (fonts / colormaps survive freezing).
- user data (SQLite / logs / reports) is written to the platform user
  data directory, never next to the binary (runtime.paths).
"""
import platform
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from damage_gui import __version__  # noqa: E402


def _platform_tag() -> str:
    if sys.platform == "darwin":
        return "macos-arm64" if platform.machine() == "arm64" else "macos-x64"
    if sys.platform == "win32":
        machine = platform.machine().lower()
        return "windows-arm64" if machine == "arm64" else "windows-x64"
    machine = platform.machine().lower()
    return "linux-arm64" if machine == "aarch64" else "linux-x64"


NAME = f"DamageLab-{__version__}-{_platform_tag()}"
ICON_ASSETS = SRC / "damage_gui" / "gui" / "assets"

datas = [
    (str(SRC / "damage_gui" / "qt" / "icons" / "*.svg"), "damage_gui/qt/icons"),
    (str(ICON_ASSETS / "damagelab-icon.png"), "damage_gui/gui/assets"),
    (str(ICON_ASSETS / "damagelab-icon.ico"), "damage_gui/gui/assets"),
]

hiddenimports = [
    "PySide6.QtSvg",
    "matplotlib.backends.backend_qtagg",
]

# Legacy Tk desktop, web backend and unused Qt modules stay out of the
# bundle.  damage_gui.gui.resources (icon shim) is still collected —
# it does not import tkinter itself.
excludes = [
    "tkinter",
    "_tkinter",
    "damage_gui.gui.main_window",
    "damage_gui.desktop",
    "damage_gui.webapp",
    "fastapi",
    "uvicorn",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTextToSpeech",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
]

a = Analysis(
    [str(SRC / "damage_gui" / "qt" / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DamageLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_ASSETS / "damagelab-icon.ico") if sys.platform != "darwin" else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=NAME,
)

if sys.platform == "darwin":
    icns = ROOT / "build" / "damagelab-icon.icns"
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=str(icns) if icns.is_file() else None,
        bundle_identifier="com.damagelab.DamageLab",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "CFBundleName": "DamageLab",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
