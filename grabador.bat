@echo off
cd /d "%~dp0"
set "SCRIPT=%~dp0record_gui.py"
set "PY="

if exist "%~dp0venv\Scripts\pythonw.exe" set "PY=%~dp0venv\Scripts\pythonw.exe"
if not defined PY if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"

if not defined PY (
    echo No se encontro Python. Instala Python 3.11 o superior y anadelo al PATH.
    echo Tambien puedes crear el entorno virtual con: python -m venv venv
    pause
    exit /b 1
)

start "" "%PY%" "%SCRIPT%"
