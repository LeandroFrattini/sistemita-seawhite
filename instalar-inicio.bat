@echo off
REM ============================================================
REM  Deja la app instalada para que arranque SOLA con la PC,
REM  sin ventana negra. Ejecutar UNA sola vez en la PC-servidor.
REM  (clic derecho -> Ejecutar como administrador)
REM ============================================================
cd /d %~dp0

if not exist .venv (
  echo Preparando el entorno por primera vez...
  py -3 -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
)

schtasks /create /tn "Lineup Sea White" ^
  /tr "wscript.exe \"%~dp0run-oculto.vbs\"" ^
  /sc onlogon /rl highest /f

echo.
echo Tarea creada. La app va a arrancar sola cada vez que se inicie sesion.
echo Para arrancarla ahora mismo sin reiniciar:
echo     schtasks /run /tn "Lineup Sea White"
echo Para desinstalarla:
echo     schtasks /delete /tn "Lineup Sea White" /f
echo.
pause
