@echo off
title LSMS Pipeline - Initial Setup

echo ===================================================
echo       LSMS Pipeline - Environment Setup
echo ===================================================
echo.
echo Checking for Python...
python --version >nul 2>&1

IF %ERRORLEVEL% NEQ 0 (
    echo Python was not found on this computer.
    echo Downloading Python 3.12 (this may take a moment)...
    curl -o "%~dp0python_installer.exe" https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe
    
    echo Installing Python silently in the background...
    echo Please wait, this usually takes 1 to 2 minutes. Do not close this window.
    start /wait "" "%~dp0python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
    
    echo Cleaning up installer...
    del "%~dp0python_installer.exe"
    
    echo Python installed successfully!
    
    :: Point to the newly installed Python
    set PY_CMD="%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
) ELSE (
    echo Python is already installed!
    set PY_CMD=python
)

echo.
echo ===================================================
echo Installing/Checking required packages...
echo ===================================================
%PY_CMD% -m pip install -r "%~dp0requirements.txt"

echo.
echo ===================================================
echo Setup Complete! You can now close this window 
echo and double-click "Run LSMS Pipeline.bat" to start.
echo ===================================================
pause