@echo off
REM Personalized Environment-Aware Biomedical Monitoring System
REM Double-click this file. It works no matter which folder Windows starts in.

setlocal
cd /d "%~dp0"

echo ===============================================================
echo  Personalized Environment-Aware Biomedical Monitoring System
echo  Folder: %CD%
echo ===============================================================
echo.

REM ---- find Python -------------------------------------------------
set "PY=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found.
        echo Install Python 3.9 or newer from https://www.python.org/downloads/
        echo and tick "Add Python to PATH" during setup.
        echo.
        pause
        exit /b 1
    )
    set "PY=py"
)

REM ---- install dependencies on first run ---------------------------
%PY% -c "import fastapi, uvicorn, serial, pydantic" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies, this happens only once...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
)

echo.
echo Starting the server on http://127.0.0.1:8000
echo Close this window to stop it.
echo.

start "" http://127.0.0.1:8000
%PY% -m uvicorn app:app --host 127.0.0.1 --port 8000

echo.
echo Server stopped.
pause
endlocal
