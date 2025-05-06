@echo off
setlocal enabledelayedexpansion

set "SRC=src"
set "ARCHIVE=archive"

echo 🛠 Preparing folders...
:: Rename app/ to src/ if it exists
if exist app (
    ren app src
)

:: Ensure required folders exist
mkdir %SRC% 2>nul
mkdir templates 2>nul
mkdir static 2>nul
mkdir logs 2>nul
mkdir %ARCHIVE% 2>nul

echo 🧹 Moving updated files to %SRC%...

move /Y mult_bambu_monitor_T.py %SRC%\bambu_monitor.py >nul 2>&1
move /Y bambu_cloud_t.py %SRC%\main.py >nul 2>&1
move /Y wled_t.py %SRC%\wled.py >nul 2>&1
move /Y utils.py %SRC%\utils.py >nul 2>&1
move /Y constants.py %SRC%\constants.py >nul 2>&1
move /Y settings.json %SRC%\settings.json >nul 2>&1

:: Move template if exists
if exist index.html move /Y index.html templates\ >nul 2>&1

:: 🔐 Archive all other .py/.json files in the root (excluding this script)
echo 🗃 Archiving unused .py/.json files...
for %%f in (*.py *.json) do (
    if /I not "%%f"=="cleanup_and_push.bat" (
        echo Archiving: %%f
        move /Y "%%f" %ARCHIVE%\ >nul 2>&1
    )
)

:: Create .gitignore if needed
if not exist .gitignore (
    (
    echo __pycache__/
    echo *.pyc
    echo logs/
    echo .env
    echo *.log
    ) > .gitignore
)

:: Create requirements.txt if missing
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

:: Create run.py pointing to main.py
if not exist run.py (
    (
    echo from src import main
    echo.
    echo if __name__ == "__main__":
    echo     import asyncio
    echo     asyncio.run(main.main())
    ) > run.py
)

:: ✅ GitHub CLI section
echo 🔧 Committing cleanup...
git add .
git commit -m "♻️ Cleanup: rename app to src, archive unused files"
git push

:: 🔁 Create PR if not on main
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
if /I not "!BRANCH!"=="main" (
    echo 🚀 Creating Pull Request via GitHub CLI...
    gh pr create --fill
)

echo ✅ Cleanup complete.
pause
