@echo off
title Stop POS Server
cd /d "%~dp0.."
call venv\Scripts\activate.bat
python run.py --stop
pause
