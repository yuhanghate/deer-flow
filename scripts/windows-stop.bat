@echo off
REM ASCII-only for cmd on all Windows locales (no UTF-8 BOM).
REM Stops services only; no downloads.

echo ============================================
echo   Stopping DeerFlow ...
echo ============================================

taskkill /fi "WINDOWTITLE eq DeerFlow-Gateway*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq DeerFlow-LangGraph*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq DeerFlow-Frontend*" /f >nul 2>&1

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8001 " ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":2024 " ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1

echo.
echo   All services stopped.
echo.
pause
