@echo off
setlocal
REM Build the DamageLab Qt desktop release (Windows).
REM
REM Usage:
REM     scripts\build_qt_release.bat          REM python on PATH
REM     set PYTHON=.venv\Scripts\python.exe && scripts\build_qt_release.bat
REM
REM Artifact:
REM     release\DamageLab-<version>-windows-x64\    onedir, unsigned.
cd /d "%~dp0.."

set "PY=%PYTHON%"
if "%PY%"=="" set "PY=python"

%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Error: PyInstaller is required ^(pip install "pyinstaller>=6,<7"^)
    exit /b 1
)

for /f %%v in ('%PY% -c "import sys; sys.path.insert(0,'src'); from damage_gui import __version__; print(__version__)"') do set "VERSION=%%v"

if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (set "TAG=windows-arm64") else (set "TAG=windows-x64")
set "NAME=DamageLab-%VERSION%-%TAG%"
echo Building %NAME% (Qt desktop)...

%PY% -m PyInstaller scripts\damagelab-qt.spec --noconfirm --clean --distpath release --workpath build\qt
if errorlevel 1 exit /b 1

copy /Y "README.md" "release\%NAME%\README.md" >nul
copy /Y "README.en.md" "release\%NAME%\README.en.md" >nul 2>&1

echo.
echo Release package created: release\%NAME%
echo Code signature: unsigned build (no code-signing certificate)
