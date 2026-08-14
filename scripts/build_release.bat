@echo off
setlocal

REM Build a lightweight Windows release. Training data and .joblib models
REM are intentionally excluded; select them from the GUI at runtime.
cd /d "%~dp0.."

set "VERSION=v1.0.0"
set "APP_NAME=Damage-GUI-%VERSION%-win64"
set "OUTPUT_DIR=release\%APP_NAME%"

echo Building %APP_NAME% ...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onedir ^
  --name "%APP_NAME%" ^
  --paths "src" ^
  --distpath "release" ^
  --workpath "build\release" ^
  --specpath "build\release" ^
  "src\damage_gui\app.py"

if errorlevel 1 exit /b 1

copy /Y "README.md" "%OUTPUT_DIR%\README.md" >nul
echo Release package created: %OUTPUT_DIR%
