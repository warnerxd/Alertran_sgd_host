@echo off
cd /d %~dp0
echo ============================================
echo  Arrancando ALERTRAN SGD API...
echo  http://localhost:8000
echo ============================================
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
