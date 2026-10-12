@echo off
title Sari-Sari POS
cd /d "%~dp0.."
call venv\Scripts\activate.bat
python run.py --app
pause
