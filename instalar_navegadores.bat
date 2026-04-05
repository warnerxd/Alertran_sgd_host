@echo off
chcp 65001 >nul
title ALERTRAN — Instalacion inicial

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   ALERTRAN SGD — Configuracion inicial          ║
echo ║   (Ejecutar solo la primera vez)                ║
echo ╚══════════════════════════════════════════════════╝
echo.

set "SCRIPT_DIR=%~dp0"

REM ── PASO 1: Visual C++ Runtime ────────────────────────────────────────────────
echo [1/2] Verificando Visual C++ Runtime...
if exist "%SystemRoot%\System32\VCRUNTIME140.dll" (
    echo   OK - Visual C++ Runtime encontrado
) else (
    echo   Descargando Visual C++ 2022 Redistributable...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%TEMP%\vc_redist.x64.exe'" 2>nul
    if exist "%TEMP%\vc_redist.x64.exe" (
        "%TEMP%\vc_redist.x64.exe" /install /quiet /norestart
        del "%TEMP%\vc_redist.x64.exe" >nul 2>&1
        echo   Visual C++ Runtime instalado.
    ) else (
        echo   [AVISO] Descarga fallida. Instala manualmente si hay errores:
        echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
    )
)

REM ── PASO 2: Instalar Chromium ─────────────────────────────────────────────────
echo.
echo [2/2] Instalando Chromium...
echo   (puede tardar varios minutos segun la conexion)
echo.

REM Método 1: node.exe empaquetado en _internal (no requiere Python)
set "NODE=%SCRIPT_DIR%_internal\playwright\driver\node.exe"
set "PW_CLI=%SCRIPT_DIR%_internal\playwright\driver\package\bin\playwright.js"
set "BROWSERS=%LOCALAPPDATA%\ms-playwright"

if exist "%NODE%" if exist "%PW_CLI%" (
    echo   Usando node.exe empaquetado...
    set "PLAYWRIGHT_BROWSERS_PATH=%BROWSERS%"
    "%NODE%" "%PW_CLI%" install chromium
    if not errorlevel 1 goto :ok
    echo   Fallo con node.exe empaquetado, intentando con Python...
)

REM Método 2: Python del sistema
python -m playwright install chromium 2>nul
if not errorlevel 1 goto :ok

REM Método 3: py launcher
py -m playwright install chromium 2>nul
if not errorlevel 1 goto :ok

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║  [ERROR] No se pudo instalar Chromium           ║
echo ║                                                  ║
echo ║  Instala Python desde python.org y ejecuta:     ║
echo ║    python -m playwright install chromium        ║
echo ╚══════════════════════════════════════════════════╝
pause
exit /b 1

:ok
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   Instalacion completada                        ║
echo ║   Ya puedes abrir ALERTRAN.exe                  ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
