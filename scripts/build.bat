@echo off
setlocal

REM ============================================
REM DamageEfficiencyApp build script (TASK 006)
REM Usage: double-click or run in CMD
REM ============================================

cd /d "%~dp0.."

REM Activate packaging venv if it exists
if exist ".venv_pack\Scripts\activate.bat" (
    call .venv_pack\Scripts\activate.bat
) else (
    echo [WARN] .venv_pack not found, using current Python environment
)

REM Step 1: onedir + console (debug build)
echo.
echo === Building onedir + console (debug) ===
pyinstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --name "DamageEfficiencyApp" ^
  --icon "src\damage_gui\gui\assets\damagelab-icon.ico" ^
  --add-data "src\damage_gui\gui\assets\damagelab-icon.ico;damage_gui\gui\assets" ^
  --add-data "src\damage_gui\gui\assets\damagelab-icon.png;damage_gui\gui\assets" ^
  --paths "src" ^
  "src\damage_gui\desktop.py"

if errorlevel 1 (
    echo.
    echo [FAIL] Build failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo === Build succeeded ===
echo Output: dist\DamageEfficiencyApp\DamageEfficiencyApp.exe

REM Copy external data and models
echo.
echo === Copying data and models ===
xcopy /E /I /Y /Q "data" "dist\DamageEfficiencyApp\data" >nul
copy /Y "README.md" "dist\DamageEfficiencyApp\" >nul
copy /Y "README.en.md" "dist\DamageEfficiencyApp\" >nul
for %%f in (damage_model_F.joblib damage_model_M.joblib damage_model_P.joblib) do (
    if exist "%%f" copy /Y "%%f" "dist\DamageEfficiencyApp\" >nul
)

echo.
echo === Package ready ===
echo   dist\DamageEfficiencyApp\DamageEfficiencyApp.exe
echo   dist\DamageEfficiencyApp\data\
echo.
pause
