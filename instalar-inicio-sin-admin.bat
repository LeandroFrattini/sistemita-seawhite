@echo off
setlocal
cd /d %~dp0
REM ============================================================
REM  Instala la app SIN permisos de administrador.
REM  - Arranca sola al iniciar sesion (carpeta Inicio del usuario)
REM  - NO puede abrir el puerto en el firewall: eso lo tiene que
REM    hacer un admin UNA vez (ver el mensaje del final).
REM ============================================================

echo [1/4] Preparando el entorno...
if not exist .venv (
  py -3 -m venv .venv 2>nul
  if errorlevel 1 python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo *** ERROR instalando dependencias. Revisar Python / conexion. ***
  pause & exit /b 1
)

echo [2/4] Dejando que arranque sola al iniciar sesion...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
copy /y "%~dp0run-oculto.vbs" "%STARTUP%\LineupSeaWhite.vbs" >nul
if errorlevel 1 (echo   (no se pudo copiar al Inicio; igual la arranco ahora)) else (echo   OK)

echo [3/4] Intentando abrir el puerto 8010 en el firewall (puede fallar sin admin)...
netsh advfirewall firewall add rule name="Lineup Sea White 8010" ^
  dir=in action=allow protocol=TCP localport=8010 profile=private,domain >nul 2>&1
if errorlevel 1 (set FW=NO) else (set FW=SI)

echo [4/4] Arrancando ahora...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8010 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
wscript.exe "%~dp0run-oculto.vbs"

echo.
echo ============================================================
echo   La app quedo corriendo y arranca sola con la sesion.
echo   En esta PC:  http://localhost:8010
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   En la red:   http://%%a:8010
echo.
if "%FW%"=="SI" (
  echo   Puerto 8010 abierto en el firewall: OK
) else (
  echo   *** FALTA: abrir el puerto 8010 en el firewall. ***
  echo   Pedile a alguien con admin que corra UNA vez, en una consola:
  echo.
  echo     netsh advfirewall firewall add rule name="Lineup Sea White 8010" dir=in action=allow protocol=TCP localport=8010
  echo.
  echo   (o que en "Firewall de Windows -> Reglas de entrada" agregue una
  echo    regla para el puerto TCP 8010). Hasta que eso pase, las otras PC
  echo    no van a poder entrar, pero en ESTA PC ya funciona.
)
echo.
echo   Frenar:      detener.bat
echo   Sacar del inicio: borrar  "%STARTUP%\LineupSeaWhite.vbs"
echo ============================================================
pause
