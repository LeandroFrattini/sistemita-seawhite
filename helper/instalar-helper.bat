@echo off
setlocal
cd /d %~dp0
REM ============================================================
REM  Ayudante "Lineup Mailer" — se instala UNA vez por PC que
REM  vaya a mandar reportes. NO necesita admin. Necesita Outlook
REM  de escritorio y Python.
REM ============================================================

echo Preparando entorno...
if not exist .venv (
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo *** ERROR instalando pywin32. Revisar conexion / Python y reintentar. ***
  pause
  exit /b 1
)

REM postinstall de pywin32 (por las dudas, dentro del venv; si falla no importa)
if exist ".venv\Scripts\pywin32_postinstall.py" (
  python ".venv\Scripts\pywin32_postinstall.py" -install -silent >nul 2>&1
)

REM --- que arranque solo al iniciar sesion: acceso directo en carpeta Inicio ---
REM (OJO: antes se copiaba el .vbs a Inicio -- pero ese script calcula rutas
REM relativas a si mismo, asi que una vez copiado apuntaba a un .venv que
REM no existia ahi y fallaba en silencio en cada inicio de sesion. Ahora se
REM deja un acceso directo que sigue apuntando a ESTA carpeta.)
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
if exist "%STARTUP%\LineupMailer.vbs" del /q "%STARTUP%\LineupMailer.vbs" >nul 2>&1
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTUP%\LineupMailer.lnk'); $s.TargetPath='wscript.exe'; $s.Arguments='\"%HERE%\run-helper-oculto.vbs\"'; $s.WorkingDirectory='%HERE%'; $s.WindowStyle=7; $s.Save()" >nul 2>&1
if errorlevel 1 (
  echo No se pudo crear el acceso directo de Inicio, pero igual lo arranco ahora.
) else (
  echo Va a arrancar solo cada vez que inicies sesion -- no muevas esta carpeta.
)

REM --- reiniciar (frenar si ya estaba corriendo, y arrancar) ---
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
wscript.exe "%~dp0run-helper-oculto.vbs"

echo.
echo ============================================================
echo  Ayudante instalado y corriendo.
echo  Probar en el navegador:  http://127.0.0.1:8765/ping
echo  (tiene que responder  {"ok": true, ...})
echo.
echo  Sacar del inicio:  borrar el acceso directo
echo    "%STARTUP%\LineupMailer.lnk"
echo  Frenar ahora:  detener-helper.bat
echo ============================================================
pause
