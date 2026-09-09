@echo off
cd /d %~dp0
if not exist .venv (
  py -3 -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
