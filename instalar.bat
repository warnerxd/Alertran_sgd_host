@echo off
cd /d %~dp0
echo ============================================
echo  Instalando dependencias en el entorno...
echo ============================================
venv\Scripts\pip.exe install -r requirements.txt
echo.
echo ============================================
echo  Instalacion completada!
echo ============================================
pause
