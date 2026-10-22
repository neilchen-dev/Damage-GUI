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
ICON_ASSETS = SRC / "damage_gui" / "runtime" / "assets"

datas = [
    (str(SRC / "damage_gui" / "qt" / "icons" / "*.svg"), "damage_gui/qt/icons"),
    (str(ICON_ASSETS / "damagelab-icon.png"), "damage_gui/runtime/assets"),
    (str(ICON_ASSETS / "damagelab-icon.ico"), "damage_gui/runtime/assets"),
]

hiddenimports = [
    "PySide6.QtSvg",
    "matplotlib.backends.backend_qtagg",
]

# Legacy Tk desktop 已于 2026-10 移除；web backend 与未用 Qt 模块不进桌面包。
# 旧打包配置中曾排除 ``tkinter`` / ``damage_gui.gui.main_window`` —— 这些模块
# 现已不存在，留档提示即可。
excludes = [
    "damage_gui.webapp",
    "damage_gui.desktop",
    "fastapi",
    "uvicorn",
    # scikit-learn + pandas：核心算法层已用 damage_gui.model.pod._PODBasis
    # （numpy 全 SVD）+ damage_gui.data.table（取代 pd.DataFrame）实现，
    # 都不再进入桌面分发包（约 -35MB+69MB）。
    # 旧 joblib 模型反序列化需要 sklearn、旧消融实验脚本需要 pandas 时，
    # 请改用 pip 安装 'damage-gui[data-science]' 而非桌面包。
    "sklearn",
    "sklearn.decomposition",
    "sklearn.metrics",
    "sklearn.model_selection",
    "sklearn.utils",
    "sklearn.ensemble",
    "sklearn.tree",
    "sklearn.svm",
    "sklearn.linear_model",
    "sklearn.neighbors",
    "sklearn.cluster",
    "sklearn.preprocessing",
    "sklearn.pipeline",
    "sklearn.base",
    "pandas",
    "pandas._libs",
    "pandas._libs.tslibs",
    "pandas.core",
    "pandas.io",
    "pandas.errors",
    "pandas.util",
    "pandas.testing",
    "scipy.cluster",  # sklearn 专属依赖，本项目不使用
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
