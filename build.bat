@echo off
chcp 65001 >nul
title ALERTRAN — Build

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║         ALERTRAN SGD — Generar EXE              ║
echo ╠══════════════════════════════════════════════════╣
echo ║  [1] Archivo unico  ALERTRAN_Setup.exe  ~94 MB  ║
echo ║      (todo en un exe, abre en ~10 seg)          ║
echo ║                                                  ║
echo ║  [2] Carpeta        ALERTRAN\          ~252 MB  ║
echo ║      (mas rapido al abrir)                      ║
echo ╚══════════════════════════════════════════════════╝
echo.
set /p OPCION="Elige [1] o [2]: "

if "%OPCION%"=="1" goto :onefile
if "%OPCION%"=="2" goto :onedir
echo Opcion invalida.
pause & exit /b 1

REM ── Argumentos comunes ────────────────────────────────────────────────────────
:build_common
REM Icono (se usa si existe assets\alertran.ico)
set ICON_FLAG=
if exist assets\alertran.ico set ICON_FLAG=--icon assets\alertran.ico

set COMMON=main.py --windowed --noconfirm --clean --exclude-module PyQt6 --exclude-module PyQt5 --add-data "assets;assets" --add-data "config;config" --add-data "utils;utils" --hidden-import qasync --hidden-import openpyxl --hidden-import openpyxl.cell._writer --hidden-import openpyxl.drawing.spreadsheet_drawing --hidden-import openpyxl.styles.builtins --hidden-import PySide6.QtSvg --hidden-import PySide6.QtSvgWidgets --hidden-import PySide6.QtNetwork --hidden-import winreg --hidden-import ctypes.wintypes --collect-all playwright --collect-submodules qasync --runtime-hook rthook_playwright.py --noupx %ICON_FLAG%
goto %GOTO_LABEL%

:onefile
echo.
echo [1/2] Limpiando...
if exist dist\ALERTRAN_Setup.exe del /q dist\ALERTRAN_Setup.exe
if exist build\ALERTRAN_Setup rmdir /s /q build\ALERTRAN_Setup

set GOTO_LABEL=run_onefile
goto :build_common

:run_onefile
echo [2/2] Compilando archivo unico...
python -m PyInstaller %COMMON% --onefile --name ALERTRAN_Setup
if errorlevel 1 ( echo [ERROR] & pause & exit /b 1 )
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║  LISTO: dist\ALERTRAN_Setup.exe  (~94 MB)       ║
echo ║  Solo necesita instalar_navegadores.bat          ║
echo ║  en la maquina destino (primera vez)            ║
echo ╚══════════════════════════════════════════════════╝
pause & exit /b 0

:onedir
echo.
echo [1/3] Limpiando...
if exist dist\ALERTRAN rmdir /s /q dist\ALERTRAN
if exist build\ALERTRAN rmdir /s /q build\ALERTRAN

set GOTO_LABEL=run_onedir
goto :build_common

:run_onedir
echo [2/3] Compilando carpeta...
python -m PyInstaller %COMMON% --name ALERTRAN
if errorlevel 1 ( echo [ERROR] & pause & exit /b 1 )

echo [3/3] Copiando DLLs de runtime...
python -c "import shutil,pathlib; root=pathlib.Path('dist/ALERTRAN'); [shutil.copy2(root/'_internal'/d, root/d) for d in ['VCRUNTIME140.dll','VCRUNTIME140_1.dll','python313.dll','python3.dll'] if (root/'_internal'/d).exists() and not (root/d).exists()]"

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║  LISTO: dist\ALERTRAN\ALERTRAN.exe  (~252 MB)   ║
echo ║  Copiar toda la carpeta dist\ALERTRAN\          ║
echo ╚══════════════════════════════════════════════════╝
pause & exit /b 0
