@echo off
REM One-time setup: installs Python if it isn't already here, then the
REM packages the pipeline needs. Only has to be run once per computer.
REM
REM You can skip this entirely if Python is already installed -- the main
REM launcher installs missing packages by itself.

title LSMS Pipeline - Initial Setup
cd /d "%~dp0"

echo ===================================================
echo       LSMS Pipeline - Environment Setup
echo ===================================================
echo.
echo Checking for Python...

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo Python was not found. Downloading Python 3.12...
    curl -L -o "%~dp0python_installer.exe" https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe
    if errorlevel 1 (
        echo.
        echo The download failed. Check the internet connection, or install
        echo Python yourself from python.org and tick "Add Python to PATH".
        echo.
        pause
        exit /b 1
    )

    echo Installing Python. This usually takes 1 to 2 minutes.
    echo Do not close this window.
    start /wait "" "%~dp0python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
    del "%~dp0python_installer.exe"

    REM PATH won't refresh in this window, so use the install path directly.
    set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if not exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        echo.
        echo Python was installed but could not be located automatically.
        echo Close this window, open it again, and re-run this file.
        echo.
        pause
        exit /b 1
    )
    echo Python installed.
) else (
    echo Python is already installed.
)

echo.
echo ===================================================
echo Installing required packages...
echo ===================================================
%PY% -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo The packages could not be installed. Check the internet connection
    echo and run this file again.
    echo.
    pause
    exit /b 1
)

echo.
echo Checking everything imports...
%PY% -c "import requests, pandas, openpyxl, matplotlib, tkinter; print('  all packages OK')"
if errorlevel 1 (
    echo.
    echo Something is still missing. The message above says what.
    echo.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo Setup complete. Close this window and double-click
echo "LSMS Impact Analysis.bat" to start.
echo ===================================================
pause
