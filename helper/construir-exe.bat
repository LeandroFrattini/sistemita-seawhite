@echo off
REM ============================================================
REM  Reconstruye el ayudante como .exe y arma el zip descargable
REM  en app\static\downloads\ayudante-outlook.zip.
REM  Correr desde una PC con Python + Outlook (para probarlo),
REM  con el venv de esta carpeta ya armado (instalar-helper.bat
REM  clasico, o "python -m venv .venv" + "pip install -r
REM  requirements.txt" a mano).
REM ============================================================
cd /d %~dp0

if not exist .venv (
  echo No existe helper\.venv -- creandolo...
  py -3 -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

pip install -q pyinstaller

echo Limpiando builds anteriores...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
rmdir /s /q paquete 2>nul
del /q lineup_mailer.spec 2>nul

echo Compilando lineup_mailer.exe...
pyinstaller --onefile --noconsole --name lineup_mailer ^
  --hidden-import win32timezone ^
  --hidden-import win32com.client ^
  --collect-submodules win32com ^
  lineup_mailer.py

if not exist dist\lineup_mailer.exe (
  echo *** FALLO LA COMPILACION ***
  pause
  exit /b 1
)

echo Armando el paquete...
mkdir paquete
copy /y dist\lineup_mailer.exe paquete\ >nul
copy /y paquete-src\instalar-helper.bat paquete\ >nul
copy /y paquete-src\detener-helper.bat paquete\ >nul
copy /y paquete-src\LEEME.md paquete\ >nul

if not exist ..\app\static\downloads mkdir ..\app\static\downloads
powershell -NoProfile -Command "Compress-Archive -Path paquete\* -DestinationPath '..\app\static\downloads\ayudante-outlook.zip' -Force"

echo.
echo ============================================================
echo  Listo: app\static\downloads\ayudante-outlook.zip
echo  (se descarga solo, la app ya lo sirve desde /static/downloads/)
echo ============================================================
pause
