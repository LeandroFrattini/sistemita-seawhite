@echo off
setlocal
REM ============================================================
REM  Ayudante "Lineup Mailer" — version .exe, sin Python.
REM  Doble clic normal (NO admin). Necesita Outlook de escritorio.
REM ============================================================
cd /d %~dp0

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo Copiando el ayudante a la carpeta de Inicio...
copy /y "%~dp0lineup_mailer.exe" "%STARTUP%\LineupMailer.exe" >nul
if errorlevel 1 (
  echo No se pudo copiar a Inicio. Lo arranco igual desde aca esta vez.
  set "RUNFROM=%~dp0lineup_mailer.exe"
) else (
  echo Listo: va a arrancar solo cada vez que inicies sesion.
  set "RUNFROM=%STARTUP%\LineupMailer.exe"
)

REM frenar una version vieja si estaba corriendo
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1

echo Arrancando...
start "" "%RUNFROM%"

timeout /t 2 >nul
echo.
echo ============================================================
echo  Probar en el navegador:  http://127.0.0.1:8765/ping
echo  (tiene que responder  {"ok": true, ...})
echo.
echo  Frenar:      detener-helper.bat
echo  Sacar del inicio: borrar "%STARTUP%\LineupMailer.exe"
echo ============================================================
pause
