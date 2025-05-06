@echo off
setlocal enabledelayedexpansion

:: === Configuration ===
set "SRC=src"
set "ARCHIVE=archive"

:: === Step 1: Rename 'app' to 'src' if it exists ===
if exist app (
    ren app src
)

:: === Step 2: Ensure required directories exist ===
mkdir %SRC% 2>nul
mkdir templates 2>nul
mkdir static 2>nul
mkdir logs 2>nul
mkdir %ARCHIVE% 2>nul

:: === Step 3: Move updated files into 'src' ===
move /Y mult_bambu_monitor_T.py %SRC%\bambu_monitor.py >nul 2>&1
move /Y bambu_cloud_t.py %SRC%\main.py >nul 2>&1
move /Y wled_t.py %SRC%\wled.py >nul 2>&1
move /Y utils.py %SRC%\utils.py >nul 2>&1
move /Y constants.py %SRC%\constants.py >nul 2>&1
move /Y settings.json %SRC%\settings.json >nul 2>&1

:: === Step 4: Move 'index.html' to 'templates' if it exists ===
if exist index.html move /Y index.html templates\ >nul 2>&1

:: === Step 5: Archive unused .py and .json files ===
for %%f in (*.py *.json) do (
    if /I not "%%f"=="cleanup_and_push.bat" (
        echo Archiving: %%f
        move /Y "%%f" %ARCHIVE%\ >nul 2>&1
    )
)

:: === Step 6: Create '.gitignore' if it doesn't exist ===
if not exist .gitignore (
    (
    echo __pycache__/
    echo *.pyc
    echo logs/
    echo .env
    echo *.log
    ) > .gitignore
)

:: === Step 7: Create 'requirements.txt' if it doesn't exist ===
if not exist requirements.txt (
    (
    echo aiohttp
    echo aiomqtt
    echo quart
    echo chump
    echo tzlocal
    echo cloudscraper
    echo hypercorn
    ) > requirements.txt
)

:: === Step 8: Create 'run.py' pointing to 'main.py' ===
if not exist run.py (
    (
    echo from src import main
    echo.
    echo if __name__ == "__main__":
    echo     import asyncio
    echo     asyncio.run(main.main())
    ) > run.py
)

:: === Step 9: Git commit and push ===
git add .
git commit -m "Refactor: rename app to src, archive unused files"
git push

:: === Step 10: Create a pull request if not on 'main' branch ===
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
if /I not "!BRANCH!"=="main" (
    gh pr create --fill
)

echo Cleanup and push complete.
pause
