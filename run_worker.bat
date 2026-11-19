@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
call set_env.bat
python worker.py
pause