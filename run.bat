@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (py -3 -m pip install -q -r requirements.txt & py -3 main.py %*) || (python -m pip install -q -r requirements.txt & python main.py %*)
