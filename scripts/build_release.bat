@echo off
setlocal

REM Build a lightweight Windows release. Training data and .joblib models
REM are intentionally excluded; select them from the GUI at runtime.
cd /d "%~dp0.."

set "VERSION=v2.1.0"
set "APP_NAME=Damage-GUI-%VERSION%-win64"
set "PROJECT_ROOT=%CD%"
set "SOURCE_DIR=%PROJECT_ROOT%\src"
set "ICON_DIR=%SOURCE_DIR%\damage_gui\gui\assets"
set "DIST_DIR=%PROJECT_ROOT%\release"
set "WORK_DIR=%PROJECT_ROOT%\build\release"
set "OUTPUT_DIR=%DIST_DIR%\%APP_NAME%"

echo Building %APP_NAME% ...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name "%APP_NAME%" ^
  --icon "%ICON_DIR%\damagelab-icon.ico" ^
  --add-data "%ICON_DIR%\damagelab-icon.ico;damage_gui\gui\assets" ^
  --add-data "%ICON_DIR%\damagelab-icon.png;damage_gui\gui\assets" ^
  --paths "%SOURCE_DIR%" ^
  --distpath "%DIST_DIR%" ^
  --workpath "%WORK_DIR%" ^
  --specpath "%WORK_DIR%" ^
  "%SOURCE_DIR%\damage_gui\desktop.py"

if errorlevel 1 exit /b 1

copy /Y "README.md" "%OUTPUT_DIR%\README.md" >nul
copy /Y "README.en.md" "%OUTPUT_DIR%\README.en.md" >nul
echo Release package created: %OUTPUT_DIR%
