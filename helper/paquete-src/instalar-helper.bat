@echo off
setlocal
REM ============================================================
REM  Ayudante "Lineup Mailer" — version .exe, sin Python.
REM  Doble clic normal (NO admin). Necesita Outlook de escritorio.
REM
REM  IMPORTANTE: dejar esta carpeta en un lugar fijo (no Descargas,
REM  no una carpeta temporal) ANTES de instalar -- el acceso directo
REM  de inicio apunta para aca, si despues movés o borrás la carpeta
REM  el ayudante deja de arrancar solo.
REM ============================================================
cd /d %~dp0

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

REM limpia una instalacion vieja rota: antes se COPIABA el .exe a Inicio,
REM y algunos antivirus lo ponian en cuarentena ahi apenas se reiniciaba
REM la PC (por eso habia que reinstalar cada vez) -- ahora se deja un
REM acceso directo que apunta al .exe original en esta carpeta
if exist "%STARTUP%\LineupMailer.exe" del /q "%STARTUP%\LineupMailer.exe" >nul 2>&1

echo Creando acceso directo de inicio...
powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTUP%\LineupMailer.lnk'); $s.TargetPath='%HERE%\lineup_mailer.exe'; $s.WorkingDirectory='%HERE%'; $s.WindowStyle=7; $s.Save()" >nul 2>&1
if errorlevel 1 (
  echo No se pudo crear el acceso directo de inicio. Lo arranco igual desde aca esta vez.
) else (
  echo Listo: va a arrancar solo cada vez que inicies sesion.
)

REM frenar una version vieja si estaba corriendo
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8765 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1

echo Arrancando...
start "" "%HERE%\lineup_mailer.exe"

timeout /t 2 >nul
echo.
echo ============================================================
echo  Probar en el navegador:  http://127.0.0.1:8765/ping
echo  (tiene que responder  {"ok": true, ...})
echo.
echo  Si "Abrir en Outlook" deja de andar despues de reiniciar la PC,
echo  lo mas probable es que el antivirus haya bloqueado o borrado
echo  lineup_mailer.exe -- revisa el historial de proteccion /
echo  cuarentena de Windows Defender y agrega esta carpeta como
echo  excepcion si aparece ahi.
echo.
echo  Frenar:           detener-helper.bat
echo  Sacar del inicio: borrar "%STARTUP%\LineupMailer.lnk"
echo ============================================================
pause
