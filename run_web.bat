@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
call set_env.bat
python app.py
pause