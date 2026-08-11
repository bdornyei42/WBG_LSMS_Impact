@echo off
REM Double-click to save your work: stages everything, commits, and pushes to
REM GitHub. Run this whenever you want your changes backed up and synced.

title LSMS Pipeline - Save to GitHub
cd /d "%~dp0"

echo ===================================================
echo       Save changes to GitHub
echo ===================================================
echo.

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo This folder is not a git repository.
    echo Make sure save.bat sits inside the cloned WBG_LSMS_Impact folder.
    echo.
    pause
    exit /b 1
)

echo Rebuilding the dashboard (docs\) from the latest results...
where python >nul 2>&1
if not errorlevel 1 (
    python build_site.py
) else (
    echo   Skipped -- python not found on PATH. The dashboard may be stale.
)
echo.

echo Checking for changes...
git add -A

git diff --cached --quiet
if not errorlevel 1 (
    echo.
    echo Nothing to save -- no changes since the last save.
    echo.
    pause
    exit /b 0
)

echo.
echo Changed files:
git diff --cached --name-status
echo.

set "MSG="
set /p MSG=Describe what changed (or press Enter for a default message):
if "%MSG%"=="" set "MSG=Update pipeline files"

echo.
echo Committing...
git commit -m "%MSG%"
if errorlevel 1 (
    echo.
    echo Commit failed. See the message above.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"

echo.
echo Pushing to GitHub (%BRANCH%)...
git push origin %BRANCH%
if errorlevel 1 (
    echo.
    echo Push failed. Check your internet connection and GitHub access,
    echo then run save.bat again -- your commit is safely saved locally
    echo either way.
    echo.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo Saved and pushed to GitHub successfully.
echo ===================================================
pause
