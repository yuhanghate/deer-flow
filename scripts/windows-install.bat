@echo off
REM DeerFlow Windows one-click install. ASCII-only for cmd.exe (no UTF-8 BOM).
REM Default: China-friendly mirrors for PyPI, Node MSI, npm/pnpm (no VPN).
REM To force official sites only:  set DEERFLOW_USE_OFFICIAL=1  then run this script.
REM Pandoc: China mode uses default Aliyun OSS ZIP ^(below^). Override with DEERFLOW_PANDOC_ZIP_URL / DEERFLOW_PANDOC_MSI_URL ^(full HTTPS^).
REM Official mode ^(DEERFLOW_USE_OFFICIAL=1^): no OSS default; set URLs yourself if you want a mirror.
REM Version in OSS path must match PANDOC_VER ^(MSI optional, ZIP for portable no-admin^).
setlocal enabledelayedexpansion

REM Windows PowerShell full path ^(parent PATH may omit System32 after reg merge^)
set "DF_PWSH=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "!DF_PWSH!" set "DF_PWSH=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"

set "DEERFLOW_CN=1"
if /i "!DEERFLOW_USE_OFFICIAL!"=="1" set "DEERFLOW_CN=0"

REM Pandoc portable ZIP default ^(China^): experimentexam OSS; %% encodes as %% in .bat so URL keeps %%E6%%...
if "!DEERFLOW_CN!"=="1" (
    if not defined DEERFLOW_PANDOC_ZIP_URL set "DEERFLOW_PANDOC_ZIP_URL=https://experimentexam.oss-cn-beijing.aliyuncs.com/%%E6%%A0%%87%%E8%%80%%83/tools/pandoc-3.9.0.2-windows-x86_64.zip"
)

echo.
echo ============================================
echo   DeerFlow - Windows one-click setup
echo ============================================
echo.
if "!DEERFLOW_CN!"=="1" (
    echo   Using China mirrors ^(PyPI Aliyun, Python SJTU/USTC, Node npmmirror^).
    echo   Override: set UV_INDEX_URL / UV_PYTHON_INSTALL_MIRROR before run.
    echo   Official only: set DEERFLOW_USE_OFFICIAL=1 then re-run.
    echo.
)

REM ---- uv / Python download mirrors (session only; child processes inherit) ----
REM PyPI: Aliyun ^(often reachable where Tsinghua is blocked^). Others: mirrors.cloud.tencent.com/pypi/simple
REM Python .zip: github-release mirrors. Step 2 retries USTC then official GitHub if needed.
if "!DEERFLOW_CN!"=="1" (
    if not defined UV_INDEX_URL set "UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"
    if not defined UV_PYTHON_INSTALL_MIRROR set "UV_PYTHON_INSTALL_MIRROR=https://mirror.sjtu.edu.cn/github-release/astral-sh/python-build-standalone/releases/download"
)

REM ---- project root ----
cd /d "%~dp0.."
set "PROJECT_DIR=%cd%"

echo -- Step 1: uv ^(Python toolchain^) --
echo.

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing uv ...
    set "UV_INSTALLED=0"
    if "!DEERFLOW_CN!"=="1" (
        where winget >nul 2>&1
        if !errorlevel! equ 0 (
            winget install -e --id astral-sh.uv --accept-package-agreements --accept-source-agreements --silent >nul 2>&1
            if !errorlevel! equ 0 set "UV_INSTALLED=1"
        )
    )
    if "!UV_INSTALLED!"=="0" (
        "%DF_PWSH%" -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex" >nul 2>&1
    )
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;!PATH!"
    where uv >nul 2>&1
    if %errorlevel% neq 0 (
        where python >nul 2>&1
        if !errorlevel! equ 0 (
            echo   Trying pip install uv ^(Aliyun PyPI^) ...
            python -m pip install -U uv -i https://mirrors.aliyun.com/pypi/simple/ --quiet
        )
    )
    where uv >nul 2>&1
    if %errorlevel% neq 0 (
        echo   [ERROR] uv install failed. Check network or use VPN once for first install.
        pause
        exit /b 1
    )
    for /f "tokens=*" %%v in ('uv --version 2^>^&1') do echo   %%v installed
) else (
    for /f "tokens=*" %%v in ('uv --version 2^>^&1') do echo   %%v already installed
)

echo.
echo -- Step 2: Python 3.12 via uv --
echo.

echo   Checking Python ...
uv python install 3.12 >nul 2>&1
if %errorlevel% neq 0 (
    if "!DEERFLOW_CN!"=="1" (
        echo   [WARN] Retrying with USTC github-release mirror ...
        set "UV_PYTHON_INSTALL_MIRROR=https://mirrors.ustc.edu.cn/github-release/astral-sh/python-build-standalone/releases/download"
        uv python install 3.12 >nul 2>&1
    )
)
if %errorlevel% neq 0 (
    if "!DEERFLOW_CN!"=="1" (
        echo   [WARN] Retrying without mirror ^(direct GitHub; may need VPN^) ...
        set "UV_PYTHON_INSTALL_MIRROR="
        uv python install 3.12 >nul 2>&1
    )
)
if %errorlevel% neq 0 (
    echo   [ERROR] Python 3.12 install failed. Try: set DEERFLOW_USE_OFFICIAL=1 or set UV_PYTHON_INSTALL_MIRROR= manually.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('uv python find 3.12 2^>^&1 ^| findstr /i /v /c:"warning:"') do (
    echo   Python 3.12: %%v
)

echo.
echo -- Step 3: Node.js 22 --
echo.

set NODE_OK=0
where node >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=1 delims=." %%m in ('node -v 2^>^&1') do (
        set "NODE_VER=%%m"
        set "NODE_VER=!NODE_VER:v=!"
    )
    if !NODE_VER! geq 22 (
        set NODE_OK=1
        for /f "tokens=*" %%v in ('node -v 2^>^&1') do echo   Node.js %%v OK
    )
)

if !NODE_OK! equ 0 (
    echo   Installing Node.js 22 ...
    where winget >nul 2>&1
    if %errorlevel% equ 0 (
        winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --silent >nul 2>&1
        if %errorlevel% equ 0 (
            echo   Node.js installed via winget
            for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
            for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
            set "PATH=!SYS_PATH!;!USR_PATH!;%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin"
            set NODE_OK=1
        )
    )

    if !NODE_OK! equ 0 (
        set "NODE_MSI=%TEMP%\nodejs-install.msi"
        set "NODE_DL_OK=0"
        if "!DEERFLOW_CN!"=="1" (
            echo   Downloading Node from npmmirror ...
            "%DF_PWSH%" -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://npmmirror.com/mirrors/node/v22.15.0/node-v22.15.0-x64.msi' -OutFile '!NODE_MSI!'" 2>nul
            if exist "!NODE_MSI!" set "NODE_DL_OK=1"
        )
        if "!NODE_DL_OK!"=="0" (
            echo   Downloading Node from nodejs.org ...
            "%DF_PWSH%" -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://nodejs.org/dist/v22.15.0/node-v22.15.0-x64.msi' -OutFile '!NODE_MSI!'" 2>nul
        )
        if exist "!NODE_MSI!" (
            echo   Running silent Node.js install ...
            msiexec /i "!NODE_MSI!" /qn /norestart
            del "!NODE_MSI!" >nul 2>&1
            for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
            for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
            set "PATH=!SYS_PATH!;!USR_PATH!;%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin"
            echo   Node.js install done
            set NODE_OK=1
        ) else (
            echo   [ERROR] Node.js download failed.
            echo          Install LTS from https://nodejs.org then run this script again.
            pause
            exit /b 1
        )
    )
)

REM Same folder as node.exe so npm.cmd / corepack.cmd resolve ^(some PATH setups omit this^)
for /f "delims=" %%N in ('where node 2^>nul') do (
    set "PATH=%%~dpN;%PATH%"
    goto :deerflow_nodepath_done
)
:deerflow_nodepath_done

echo.
echo -- Step 4: pnpm --
echo.

where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing pnpm ...
    where node >nul 2>&1
    if !errorlevel! equ 0 (
        call corepack enable >nul 2>&1
        call corepack prepare pnpm@latest --activate >nul 2>&1
    )
    where pnpm >nul 2>&1
    if !errorlevel! neq 0 (
        where npm >nul 2>&1
        if !errorlevel! equ 0 call npm install -g pnpm >nul 2>&1
    )
    where pnpm >nul 2>&1
    if !errorlevel! neq 0 (
        echo   corepack/npm failed, trying winget ...
        winget install -e --id pnpm.pnpm --accept-package-agreements --accept-source-agreements --silent >nul 2>&1
    )
    where pnpm >nul 2>&1
    if %errorlevel% neq 0 (
        echo   [ERROR] pnpm install failed.
        pause
        exit /b 1
    )
    for /f "tokens=*" %%v in ('pnpm --version 2^>^&1') do echo   pnpm %%v installed
) else (
    for /f "tokens=*" %%v in ('pnpm --version 2^>^&1') do echo   pnpm %%v OK
)

REM npm/pnpm registry for China ^(saved to user config, one-time^)
if "!DEERFLOW_CN!"=="1" (
    echo   Setting npm/pnpm registry to npmmirror ^(user profile^) ...
    where npm >nul 2>&1
    if !errorlevel! equ 0 call npm config set registry https://registry.npmmirror.com >nul 2>&1
    call pnpm config set registry https://registry.npmmirror.com >nul 2>&1
)

echo.
echo -- Step 5: Project dependencies --
echo.

echo   [1/3] Backend ^(uv sync^) ...
cd /d "%PROJECT_DIR%\backend"
uv sync --quiet
if %errorlevel% neq 0 (
    echo   [ERROR] Backend deps failed
    pause
    exit /b 1
)
echo         Backend OK
cd /d "%PROJECT_DIR%"

echo   [2/3] Frontend ^(pnpm install^) ...
cd /d "%PROJECT_DIR%\frontend"
call pnpm install --silent
if %errorlevel% neq 0 (
    echo   [ERROR] Frontend deps failed
    pause
    exit /b 1
)
echo         Frontend OK
cd /d "%PROJECT_DIR%"

echo   [3/3] Skill-related packages ^(pandoc + Python extras + global pnpm^) ...

REM Pandoc: pinned release ^(update PANDOC_VER when bumping; keep CDN file names in sync^)
set "PANDOC_VER=3.9.0.2"
set "PANDOC_MSI=%TEMP%\deerflow-pandoc-%PANDOC_VER%.msi"
set "PANDOC_ZIP=%TEMP%\deerflow-pandoc-%PANDOC_VER%.zip"
set "PANDOC_DIR=%USERPROFILE%\.local\pandoc"

where pandoc >nul 2>&1
if %errorlevel% equ 0 (
    echo         pandoc already on PATH
    goto :pandoc_done
)

echo         Installing pandoc ^(%PANDOC_VER%^) ...

REM In China mode with a CDN ZIP URL, go straight to portable ZIP ^(fastest^). Skip winget entirely.
if "!DEERFLOW_CN!"=="1" if defined DEERFLOW_PANDOC_ZIP_URL goto :pandoc_try_zip

REM Official mode ^(or no CDN ZIP^): try winget first, then fall through to MSI/ZIP download.
where winget >nul 2>&1
if %errorlevel% equ 0 (
    echo         Trying winget ^(JohnMacFarlane.Pandoc^) ...
    winget install -e --id JohnMacFarlane.Pandoc --accept-package-agreements --accept-source-agreements --silent >nul 2>&1
    call :deerflow_refresh_path
)
where pandoc >nul 2>&1
if %errorlevel% equ 0 goto :pandoc_ok

echo         winget did not leave pandoc on PATH, trying MSI download ...

if exist "%PANDOC_MSI%" del /f /q "%PANDOC_MSI%" >nul 2>&1
if "!DEERFLOW_CN!"=="1" (
    "%DF_PWSH%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $v='%PANDOC_VER%'; $o=Join-Path $env:TEMP ('deerflow-pandoc-'+$v+'.msi'); $urls=@(); if($env:DEERFLOW_PANDOC_MSI_URL){$urls+=$env:DEERFLOW_PANDOC_MSI_URL}; $urls+=@(('https://mirror.sjtu.edu.cn/github-release/jgm/pandoc/releases/download/{0}/pandoc-{0}-windows-x86_64.msi' -f $v),('https://github.com/jgm/pandoc/releases/download/{0}/pandoc-{0}-windows-x86_64.msi' -f $v)); $ok=$false; foreach($u in $urls){ try{ $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing; if((Get-Item -LiteralPath $o).Length -ge 1000000){$ok=$true;break}}catch{}}; if(-not $ok){ exit 1 }"
) else (
    "%DF_PWSH%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $v='%PANDOC_VER%'; $o=Join-Path $env:TEMP ('deerflow-pandoc-'+$v+'.msi'); $urls=@(); if($env:DEERFLOW_PANDOC_MSI_URL){$urls+=$env:DEERFLOW_PANDOC_MSI_URL}; $urls+=@(('https://github.com/jgm/pandoc/releases/download/{0}/pandoc-{0}-windows-x86_64.msi' -f $v)); $ok=$false; foreach($u in $urls){ try{ $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing; if((Get-Item -LiteralPath $o).Length -ge 1000000){$ok=$true;break}}catch{}}; if(-not $ok){ exit 1 }"
)
if not exist "%PANDOC_MSI%" (
    echo         [WARN] pandoc MSI download failed, will try portable ZIP.
    goto :pandoc_try_zip
)
echo         Running pandoc MSI ^(silent, may prompt UAC^) ...
start /wait msiexec /i "%PANDOC_MSI%" /qn /norestart
del /f /q "%PANDOC_MSI%" >nul 2>&1
call :deerflow_refresh_path
timeout /t 2 /nobreak >nul
where pandoc >nul 2>&1
if %errorlevel% equ 0 goto :pandoc_ok

:pandoc_try_zip
echo         Downloading portable pandoc ZIP ...
if exist "%PANDOC_ZIP%" del /f /q "%PANDOC_ZIP%" >nul 2>&1
if "!DEERFLOW_CN!"=="1" (
    "%DF_PWSH%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $v='%PANDOC_VER%'; $o=Join-Path $env:TEMP ('deerflow-pandoc-'+$v+'.zip'); $urls=@(); if($env:DEERFLOW_PANDOC_ZIP_URL){$urls+=$env:DEERFLOW_PANDOC_ZIP_URL}; $urls+=@(('https://mirror.sjtu.edu.cn/github-release/jgm/pandoc/releases/download/{0}/pandoc-{0}-windows-x86_64.zip' -f $v),('https://github.com/jgm/pandoc/releases/download/{0}/pandoc-{0}-windows-x86_64.zip' -f $v)); $ok=$false; foreach($u in $urls){ try{ $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing; if((Get-Item -LiteralPath $o).Length -ge 500000){$ok=$true;break}}catch{}}; if(-not $ok){ exit 1 }"
) else (
    "%DF_PWSH%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $v='%PANDOC_VER%'; $o=Join-Path $env:TEMP ('deerflow-pandoc-'+$v+'.zip'); $urls=@(); if($env:DEERFLOW_PANDOC_ZIP_URL){$urls+=$env:DEERFLOW_PANDOC_ZIP_URL}; $urls+=@(('https://github.com/jgm/pandoc/releases/download/{0}/pandoc-{0}-windows-x86_64.zip' -f $v)); $ok=$false; foreach($u in $urls){ try{ $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing; if((Get-Item -LiteralPath $o).Length -ge 500000){$ok=$true;break}}catch{}}; if(-not $ok){ exit 1 }"
)
if not exist "%PANDOC_ZIP%" (
    echo         [WARN] pandoc ZIP download failed.
    goto :pandoc_fail
)
"%DF_PWSH%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $v='%PANDOC_VER%'; $z=Join-Path $env:TEMP ('deerflow-pandoc-'+$v+'.zip'); $dest=Join-Path $env:USERPROFILE '.local\pandoc'; $stage=Join-Path $env:TEMP 'deerflow-pandoc-unz'; if(Test-Path $stage){Remove-Item -Recurse -Force $stage}; New-Item -ItemType Directory -Force -Path $dest | Out-Null; Expand-Archive -LiteralPath $z -DestinationPath $stage -Force; $exe=Get-ChildItem -Path $stage -Recurse -Filter pandoc.exe -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $exe){ exit 1 }; $src=$exe.DirectoryName; robocopy $src $dest /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null; if($LASTEXITCODE -ge 8){ exit 1 }; $cur=[Environment]::GetEnvironmentVariable('Path','User'); if($cur -notlike ('*'+$dest+'*')){ [Environment]::SetEnvironmentVariable('Path', $dest+';'+$cur, 'User') }"
if %errorlevel% neq 0 (
    echo         [WARN] pandoc portable install failed.
    del /f /q "%PANDOC_ZIP%" >nul 2>&1
    goto :pandoc_fail
)
del /f /q "%PANDOC_ZIP%" >nul 2>&1
call :deerflow_refresh_path
set "PATH=!PANDOC_DIR!;%PATH%"
where pandoc >nul 2>&1
if %errorlevel% equ 0 goto :pandoc_ok

:pandoc_fail
echo         [WARN] pandoc not installed. Close this window, open a new cmd, re-run install, or install Pandoc manually.
goto :pandoc_done

:pandoc_ok
for /f "tokens=*" %%v in ('pandoc --version 2^>nul ^| findstr /b /c:"pandoc"') do (
    echo         %%v OK
    goto :pandoc_done
)
echo         pandoc OK ^(restart terminal if --version fails here^)
:pandoc_done

cd /d "%PROJECT_DIR%\backend"
uv pip install --quiet --python .venv\Scripts\python.exe openpyxl defusedxml lxml pypdf pdfplumber Pillow requests python-pptx duckdb markdown fpdf2 2>nul
if %errorlevel% neq 0 (
    uv pip install --quiet openpyxl defusedxml lxml pypdf pdfplumber Pillow requests python-pptx duckdb markdown fpdf2 2>nul
)
echo         Python extras OK

cd /d "%PROJECT_DIR%"
set "GLOBAL_DOC_OK=0"
call pnpm add -g docx pptxgenjs >nul 2>&1
if !errorlevel! equ 0 set "GLOBAL_DOC_OK=1"
if "!GLOBAL_DOC_OK!"=="0" (
    where npm >nul 2>&1
    if !errorlevel! equ 0 (
        call npm install -g docx pptxgenjs >nul 2>&1
        if !errorlevel! equ 0 set "GLOBAL_DOC_OK=1"
    )
)
if "!GLOBAL_DOC_OK!"=="0" (
    echo         [NOTE] Optional: pnpm add -g docx pptxgenjs ^(or npm install -g^)
) else (
    echo         Global packages OK ^(docx pptxgenjs^)
)

echo.
echo -- Step 6: Configuration --
echo.

if exist config.yaml (
    if exist .env (
        echo   config.yaml and .env found, skipping wizard
        goto :skip_setup
    )
)

if not exist config.yaml (
    echo   First run: follow prompts for API keys.
    echo.
    cd /d "%PROJECT_DIR%\backend"
    uv run python ..\scripts\setup_wizard.py
    cd /d "%PROJECT_DIR%"
) else (
    echo   config.yaml exists
    if not exist .env (
        echo   [NOTE] Add API keys to %PROJECT_DIR%\.env
    )
)

:skip_setup

echo.
echo -- Step 7: Desktop shortcuts --
echo.

set "DESKTOP=%USERPROFILE%\Desktop"

(
echo @echo off
echo cd /d "%PROJECT_DIR%"
echo call scripts\windows-start.bat
) > "%DESKTOP%\Start-DeerFlow.bat"

(
echo @echo off
echo cd /d "%PROJECT_DIR%"
echo call scripts\windows-stop.bat
) > "%DESKTOP%\Stop-DeerFlow.bat"

echo   Desktop: Start-DeerFlow.bat  Stop-DeerFlow.bat

echo.
echo ************************************************************
echo.
echo     DeerFlow Windows setup:  SUCCESS
echo.
echo   * Backend ^(uv^) and Frontend ^(pnpm^) are ready
echo   * Desktop shortcuts created ^(Start / Stop^)
echo   * Next: this script will run windows-start.bat
echo     ^(backend + frontend dev servers^)
echo.
echo ************************************************************
echo.
echo Press any key to START DeerFlow now ^(windows-start.bat^) ...
echo Or close this window and double-click Start-DeerFlow.bat later.
pause
call "%~dp0windows-start.bat"
exit /b 0

:deerflow_refresh_path
for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
if not defined SYS_PATH set "SYS_PATH="
if not defined USR_PATH set "USR_PATH="
set "PATH=%SystemRoot%\System32;%SystemRoot%;!SYS_PATH!;!USR_PATH!;%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin"
goto :eof
