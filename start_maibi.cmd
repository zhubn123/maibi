@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "PYTHON_CMD="

for %%V in (3.13 3.12 3.11) do (
    if not defined PYTHON_CMD (
        py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -%%V"
    )
)

for /f "delims=" %%F in ('where python.exe 2^>nul') do (
    if not defined PYTHON_CMD (
        echo %%F | findstr /I "\\.venv\\Scripts\\python.exe" >nul
        if errorlevel 1 (
            "%%F" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
            if not errorlevel 1 set "PYTHON_CMD="%%F""
        )
    )
)

for %%F in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
) do (
    if not defined PYTHON_CMD (
        if exist "%%~F" (
            "%%~F" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
            if not errorlevel 1 set "PYTHON_CMD="%%~F""
        )
    )
)

if not defined PYTHON_CMD (
    echo [Maibi] Python 3.11 or newer was not found on PATH.
    echo [Maibi] Install Python 3.11+ and rerun this file.
    pause
    exit /b 1
)

echo [Maibi] Using Python:
%PYTHON_CMD% --version

if not exist ".venv\Scripts\python.exe" (
    echo [Maibi] Creating local Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :install_failed
)

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [Maibi] Existing .venv is older than Python 3.11. Recreating it...
    rmdir /s /q .venv
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :install_failed
)

".venv\Scripts\python.exe" -c "import PySide6, uvicorn, client.demo_app, server.app" >nul 2>nul
if errorlevel 1 (
    echo [Maibi] Installing or repairing dependencies...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto :install_failed
    ".venv\Scripts\python.exe" -m pip install --no-cache-dir -e ".[dev]"
    if errorlevel 1 goto :install_failed
    ".venv\Scripts\python.exe" -c "import PySide6, uvicorn, client.demo_app, server.app" >nul 2>nul
    if errorlevel 1 goto :install_failed
)

echo [Maibi] Launching Maibi...
".venv\Scripts\python.exe" -m client.launcher
exit /b %ERRORLEVEL%

:install_failed
echo [Maibi] Dependency setup failed.
echo [Maibi] Check the error output above, then rerun start_maibi.cmd.
pause
exit /b 1
