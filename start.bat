@echo off
setlocal
set "APP_DIR=%~dp0"
set "PYTHONW=%APP_DIR%.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo Python environment not found at "%APP_DIR%.venv".
    echo Set up the project as described in README.md before starting the app.
    pause
    exit /b 1
)

start "" /D "%APP_DIR%" "%PYTHONW%" "%APP_DIR%main_qt.py"
