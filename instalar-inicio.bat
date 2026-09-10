@echo off
REM ============================================================
REM  Instala la app en la PC-servidor: arranca sola con la PC
REM  (sin ventana) y abre el puerto 8010 en el firewall para
REM  que entren las demas PC de la red.
REM  >>> Ejecutar UNA vez, clic derecho -> Ejecutar como administrador <<<
REM ============================================================
cd /d %~dp0

net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Hay que ejecutarlo COMO ADMINISTRADOR.
  echo   Clic derecho en instalar-inicio.bat -> "Ejecutar como administrador".
  echo.
  pause
  exit /b 1
)

echo [1/4] Preparando el entorno...
if not exist .venv (
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo *** ERROR instalando dependencias. Revisar Python / conexion. ***
  pause & exit /b 1
)

echo [2/4] Abriendo el puerto 8010 en el firewall...
netsh advfirewall firewall delete rule name="Lineup Sea White 8010" >nul 2>&1
netsh advfirewall firewall add rule name="Lineup Sea White 8010" ^
  dir=in action=allow protocol=TCP localport=8010 profile=private,domain >nul

echo [3/4] Creando la tarea de inicio...
schtasks /create /tn "Lineup Sea White" ^
  /tr "wscript.exe \"%~dp0run-oculto.vbs\"" ^
  /sc onlogon /rl highest /f >nul

echo [4/4] Arrancando ahora...
schtasks /run /tn "Lineup Sea White" >nul

echo.
echo ============================================================
echo   LISTO. La app queda corriendo y arranca sola con la PC.
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   Direccion para las otras PC:  http://%%a:8010
echo   En esta PC:                   http://localhost:8010
echo.
echo   Frenar:      detener.bat
echo   Desinstalar: schtasks /delete /tn "Lineup Sea White" /f
echo ============================================================
pause
