@echo off
REM Detiene la app (cualquier proceso escuchando en el puerto 8010)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8010 ^| findstr LISTENING') do (
  echo Deteniendo PID %%p
  taskkill /PID %%p /F >nul 2>&1
)
echo Listo.
timeout /t 2 >nul
