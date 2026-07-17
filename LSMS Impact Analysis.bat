@echo off
REM Double-click this file to launch the LSMS pipeline with a simple window
REM instead of a command line. Requires Python to be installed (python.org)
REM and this .bat file to sit in the same folder as run_pipeline.py and
REM discover.py.

cd /d "%~dp0"
python run_pipeline.py
if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed and that
    echo this file is in the same folder as run_pipeline.py and discover.py.
    pause
)
