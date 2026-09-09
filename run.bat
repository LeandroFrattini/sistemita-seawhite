@echo off
cd /d %~dp0
title Line-up Sea White (dejar esta ventana abierta)

if not exist .venv (
  echo Instalando por primera vez, esperar un minuto...
  py -3 -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo.
echo ============================================================
echo   Line-up Sea White corriendo.
echo   Abrir en el navegador:  http://localhost:8010
echo   En otra PC de la red:   http://%COMPUTERNAME%:8010
echo   Para apagarlo: cerrar esta ventana.
echo ============================================================
echo.

start "" http://localhost:8010
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
