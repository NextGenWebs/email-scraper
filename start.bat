@echo off
title Email Scraper - Starting Services
cd /d "%~dp0"

echo ======================================================================
echo                     EMAIL SCRAPER - STARTING
echo ======================================================================
echo.

:: Check if Redis is already running
echo [1/4] Starting Redis...
tasklist /FI "IMAGENAME eq redis-server.exe" 2>NUL | find /I "redis-server.exe" >NUL
if %ERRORLEVEL%==0 (
    echo       Redis is already running
) else (
    start "Redis Server" /MIN redis\redis-server.exe
    timeout /t 2 /nobreak >nul
    echo       Redis started
)

:: Start Celery Worker
echo [2/4] Starting Celery Worker...
start "Celery Worker" /MIN cmd /c "python -m celery -A celery_app worker -Q scrape,scrape_high,ops --pool=solo --loglevel=info"
timeout /t 2 /nobreak >nul
echo       Celery Worker started

:: Start Flower (optional monitoring)
echo [3/4] Starting Flower Monitor...
start "Flower" /MIN cmd /c "python -m celery -A celery_app -b redis://localhost:6379/0 flower --port=5555"
timeout /t 2 /nobreak >nul
echo       Flower started at http://localhost:5555

:: Start Flask App
echo [4/4] Starting Flask App...
start "Flask App" cmd /c "python app.py"
timeout /t 3 /nobreak >nul
echo       Flask App started at http://localhost:5000

echo.
echo ======================================================================
echo                     ALL SERVICES STARTED
echo ======================================================================
echo.
echo   Web App:    http://localhost:5000
echo   Flower:     http://localhost:5555
echo.
echo   To stop all services, run: stop.bat
echo.
pause
