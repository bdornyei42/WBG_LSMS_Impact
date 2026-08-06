@echo off
REM Double-click to run the LSMS pipeline.
REM
REM Everything it needs lives in this folder, so the folder can be copied to
REM another computer and run there. On first launch it finds Python and
REM installs any missing packages by itself.

title LSMS Impact Analysis
cd /d "%~dp0"

REM ---- find Python -------------------------------------------------------
REM "py" is the Windows launcher and is the most reliable when several
REM versions are installed. Fall back to whatever "python" points at, then to
REM the per-user install path Initial Setup.bat uses.
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

if not defined PY (
    echo.
    echo Python was not found on this computer.
    echo.
    echo Run "Initial Setup.bat" first. It installs Python and everything
    echo else this tool needs, and only has to be done once.
    echo.
    pause
    exit /b 1
)

REM ---- check packages, install only if something is missing --------------
REM Running pip on every launch would add several seconds each time, so try
REM importing first and only reach for pip when that fails.
%PY% -c "import requests, pandas, openpyxl, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo First run on this computer, or a package is missing.
    echo Installing what's needed. This usually takes a minute...
    echo.
    %PY% -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo.
        echo The packages could not be installed automatically.
        echo Check the internet connection, or run "Initial Setup.bat".
        echo.
        pause
        exit /b 1
    )
    echo.
    echo Packages installed.
    echo.
)

REM ---- run ---------------------------------------------------------------
%PY% "%~dp0run_pipeline.py"
if errorlevel 1 (
    echo.
    echo The analysis stopped with an error. The message above says why.
    echo.
    echo If it mentions a missing file, check that this .bat is still in the
    echo same folder as run_pipeline.py, discover.py and requirements.txt.
    echo.
    pause
)
