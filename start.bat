@echo off
setlocal
set "APP_DIR=%~dp0"
set "VENV_DIR=%APP_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "DESKTOP_DIR=%APP_DIR%desktop"

if not exist "%VENV_PYTHON%" (
    echo Python environment not found. Creating "%VENV_DIR%"...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        python -m venv "%VENV_DIR%"
    )
    if not exist "%VENV_PYTHON%" (
        echo Failed to create the virtual environment. Is Python installed and on PATH?
        pause
        exit /b 1
    )
    echo Installing Python dependencies...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    "%VENV_PYTHON%" -m pip install -e "%APP_DIR%."
    if errorlevel 1 (
        echo Python dependency installation failed.
        pause
        exit /b 1
    )
)

where npm >nul 2>&1
if errorlevel 1 (
    echo npm not found. Install Node.js and Rust to run the desktop app.
    pause
    exit /b 1
)

pushd "%DESKTOP_DIR%"
if not exist "node_modules" (
    echo Installing desktop dependencies...
    call npm ci
    if errorlevel 1 (
        echo npm ci failed.
        popd
        pause
        exit /b 1
    )
)

call npm run tauri dev
popd
