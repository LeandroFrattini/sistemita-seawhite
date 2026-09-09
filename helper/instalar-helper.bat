@echo off
REM ============================================================
REM  Ayudante "Lineup Mailer" — se instala UNA vez en cada PC
REM  que vaya a mandar reportes. Necesita Outlook de escritorio.
REM ============================================================
cd /d %~dp0

echo Preparando entorno...
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

schtasks /create /tn "Lineup Mailer" ^
  /tr "wscript.exe \"%~dp0run-helper-oculto.vbs\"" ^
  /sc onlogon /f

echo.
echo Arrancando ahora...
schtasks /run /tn "Lineup Mailer"

echo.
echo Listo. El ayudante queda corriendo y arranca solo al iniciar sesion.
echo Probar: abrir en el navegador  http://127.0.0.1:8765/ping
echo Desinstalar:  schtasks /delete /tn "Lineup Mailer" /f
echo.
pause
