@echo off
setlocal enabledelayedexpansion

:: === CONFIG ===
set "SRC=src"
set "ARCHIVE=archive"

:: === Step 1: Create folder structure ===
mkdir %SRC% 2>nul
mkdir templates 2>nul
mkdir static 2>nul
mkdir logs 2>nul
mkdir %ARCHIVE% 2>nul

echo 🧹 Moving updated files to %SRC%...

:: Move updated source files
move /Y mult_bambu_monitor_T.py %SRC%\bambu_monitor.py >nul 2>&1
move /Y bambu_cloud_t.py %SRC%\main.py >nul 2>&1
move /Y wled_t.py %SRC%\wled.py >nul 2>&1
move /Y utils.py %SRC%\utils.py >nul 2>&1
move /Y constants.py %SRC%\constants.py >nul 2>&1
move /Y settings.json %SRC%\settings.json >nul 2>&1

:: Move template if present
if exist index.html move /Y index.html templates\ >nul 2>&1

:: === Step 2: Archive any other .py or .json files ===
for %%f in (*.py *.json) do (
    if not "%%f"=="cleanup_and_push.bat" (
        echo Archiving: %%f
        move /Y "%%f" %ARCHIVE%\
    )
)

:: === Step 3: Create .gitignore if needed ===
if not exist .gitignore (
    (
    echo __pycache__/
    echo *.pyc
    echo logs/
    echo .env
    echo *.log
    ) > .gitignore
)

:: === Step 4: Create requirements.txt if missing ===
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

:: === Step 5: Create run.py pointing to main.py ===
if not exist run.py (
    (
    echo from src import main
    echo.
    echo if __name__ == "__main__":
    echo     import asyncio
    echo     asyncio.run(main.main())
    ) > run.py
)

:: === Step 6: Git commit & push ===
echo 📝 Committing changes...
git add .
git commit -m "🚚 Refactor: move to src/, rename bambu_cloud_t.py to main.py"
git push

:: === Step 7: PR if not on main branch ===
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
if not "!BRANCH!"=="main" (
    echo 🔄 Creating Pull Request via GitHub CLI...
    gh pr create --fill
)

echo ✅ Repo cleanup complete.
pause
