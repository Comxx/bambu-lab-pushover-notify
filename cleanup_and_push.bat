@echo off
setlocal enabledelayedexpansion

:: Step 1: Organize Files
call :move_files

:: Step 2: Commit and Push
echo  Committing changes...
git add .
git commit -m " Clean up and reorganize repo structure"
echo  Pushing to GitHub...
git push

:: Step 3: Optional — Create a Pull Request if on a branch
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%i
if not "%BRANCH%"=="main" (
    echo  Creating Pull Request via GitHub CLI...
    gh pr create --fill
)

exit /b

:move_files
echo Cleaning and organizing your Bambu Lab Pushover Notify repo...

mkdir app 2>nul
mkdir templates 2>nul
mkdir static 2>nul
mkdir logs 2>nul
mkdir archive 2>nul

move mult_bambu_monitor_T.py app\bambu_monitor.py >nul 2>&1
move bambu_cloud_t.py app\bambu_cloud.py >nul 2>&1
move wled_t.py app\wled.py >nul 2>&1
move utils.py app\utils.py >nul 2>&1
move constants.py app\constants.py >nul 2>&1
move settings.json app\settings.json >nul 2>&1

if exist index.html move index.html templates\ >nul 2>&1

for %%f in (*_T.py *.bak *.old) do (
    if exist "%%f" move "%%f" archive\
)

(
echo __pycache__/
echo *.pyc
echo logs/
echo .env
echo *.log
) > .gitignore

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

if not exist run.py (
    (
    echo from app import bambu_monitor
    echo.
    echo if __name__ == "__main__":
    echo     import asyncio
    echo     asyncio.run(bambu_monitor.main())
    ) > run.py
)

echo  Files organized.
exit /b
