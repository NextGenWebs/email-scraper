@echo off
title Email Scraper - Stopping Services
cd /d "%~dp0"

echo ======================================================================
echo                     EMAIL SCRAPER - STOPPING
echo ======================================================================
echo.

echo [1/4] Stopping Flask App...
taskkill /FI "WINDOWTITLE eq Flask App*" /F >nul 2>&1
echo       Flask App stopped

echo [2/4] Stopping Celery Workers...
taskkill /FI "WINDOWTITLE eq Celery Worker*" /F >nul 2>&1
wmic process where "commandline like '%%celery%%'" delete >nul 2>&1
echo       Celery Workers stopped

echo [3/4] Stopping Flower...
taskkill /FI "WINDOWTITLE eq Flower*" /F >nul 2>&1
wmic process where "commandline like '%%flower%%'" delete >nul 2>&1
echo       Flower stopped

echo [4/4] Cleaning up Redis queues...
python -c "import redis; r=redis.from_url('redis://localhost:6379'); r.flushdb(); print('       Redis queues cleaned')" 2>nul || echo       Redis cleanup skipped

echo.
echo ======================================================================
echo                     ALL SERVICES STOPPED
echo ======================================================================
echo.
echo   Note: Redis server is still running (for data persistence)
echo   To stop Redis: taskkill /IM redis-server.exe /F
echo.
pause
