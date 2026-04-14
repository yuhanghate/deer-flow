@echo off
REM ASCII-only for cmd on all Windows locales (no UTF-8 BOM).
REM Same mirrors as install: child "start" processes inherit this environment.
setlocal enabledelayedexpansion

if not defined DEERFLOW_USE_OFFICIAL (
    if not defined UV_INDEX_URL set "UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"
)

echo.
echo ============================================
echo   DeerFlow - starting ...
echo ============================================
echo.

cd /d "%~dp0.."
set "PROJECT_DIR=%cd%"

set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;!PATH!"

if exist .env (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
)

if not exist config.yaml (
    if exist backend\config.yaml (
        echo   [NOTE] Using backend\config.yaml
    ) else (
        echo   [ERROR] config.yaml not found
        echo          Run scripts\windows-install.bat first
        pause
        exit /b 1
    )
)

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] uv not found. Run scripts\windows-install.bat first
    pause
    exit /b 1
)

echo   Stopping old processes on ports ...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":2024 " ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8001 " ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /pid %%p /f >nul 2>&1
timeout /t 1 /nobreak >nul

echo   [1/3] LangGraph Server port 2024 ...
start "DeerFlow-LangGraph" /min cmd /c "set PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH% && cd /d "%PROJECT_DIR%\backend" && uv run langgraph dev --host 127.0.0.1 --port 2024 --no-browser --no-reload"

echo         Waiting for LangGraph (first start may take 1-2 min) ...
call :wait_port 2024 120
if !errorlevel! equ 0 (
    echo         LangGraph ready
) else (
    echo         [WARN] LangGraph may still be starting ...
)

echo   [2/3] Gateway API port 8001 ...
start "DeerFlow-Gateway" /min cmd /c "set PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH% && set PYTHONPATH=. && cd /d "%PROJECT_DIR%\backend" && uv run uvicorn app.gateway.app:app --host 127.0.0.1 --port 8001"

echo         Waiting for Gateway ...
call :wait_port 8001 60
if !errorlevel! equ 0 (
    echo         Gateway ready
) else (
    echo         [WARN] Gateway may still be starting ...
)

echo   [3/3] Frontend port 3000 ...
start "DeerFlow-Frontend" /min cmd /c "cd /d "%PROJECT_DIR%\frontend" && pnpm run dev"

echo         Waiting for frontend (first compile ~30s) ...
call :wait_port 3000 120
if !errorlevel! equ 0 (
    echo         Frontend ready
) else (
    echo         [WARN] Frontend may still be starting ...
)

echo.
start http://127.0.0.1:3000

echo ============================================
echo   DeerFlow started
echo ============================================
echo.
echo   Open: http://127.0.0.1:3000
echo   Stop: double-click Stop-DeerFlow.bat on Desktop
echo.
pause
exit /b 0

:wait_port
set "_port=%~1"
set "_timeout=%~2"
set "_elapsed=0"
:wait_loop
if !_elapsed! geq !_timeout! (
    exit /b 1
)
timeout /t 2 /nobreak >nul
set /a _elapsed+=2
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', %_port%); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! equ 0 (
    exit /b 0
)
goto wait_loop
