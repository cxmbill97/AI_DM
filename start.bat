@echo off
:: AI Deduction Game — single-command startup script (Windows)
:: Usage: start.bat
:: Starts backend (port 8000) + frontend (port 5173) and prints access URLs.
:: Close the terminal window or press Ctrl-C to stop both servers.

echo.
echo [92m🎮 AI Deduction Game — Starting...[0m
echo.

:: ---------------------------------------------------------------------------
:: Dependency checks
:: ---------------------------------------------------------------------------

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [91mERROR: uv not found.[0m
    echo   Install: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    exit /b 1
)

where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo [91mERROR: pnpm not found.[0m
    echo   Install: npm install -g pnpm
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: API key check
:: ---------------------------------------------------------------------------

set SCRIPT_DIR=%~dp0

if not exist "%SCRIPT_DIR%backend\.env" (
    echo [91mERROR: backend\.env not found.[0m
    echo   Copy the example and add your API key:
    echo     copy backend\.env.example backend\.env
    echo   Then edit backend\.env and set MINIMAX_API_KEY.
    exit /b 1
)

findstr /c:"your_minimax_api_key_here" "%SCRIPT_DIR%backend\.env" >nul 2>&1
if %errorlevel% equ 0 (
    echo [91mERROR: backend\.env still contains the placeholder key.[0m
    echo   Edit backend\.env and replace MINIMAX_API_KEY with your real key.
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: Install dependencies
:: ---------------------------------------------------------------------------

echo [93m📦 Installing dependencies...[0m

pushd "%SCRIPT_DIR%backend"
call uv sync --quiet
if %errorlevel% neq 0 ( echo ERROR: backend install failed & exit /b 1 )
popd

pushd "%SCRIPT_DIR%frontend"
call pnpm install --silent
if %errorlevel% neq 0 ( echo ERROR: frontend install failed & exit /b 1 )
popd

echo.

:: ---------------------------------------------------------------------------
:: Detect LAN IP
:: ---------------------------------------------------------------------------

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set LAN_IP=%%a
    goto :got_ip
)
:got_ip
:: strip leading space
set LAN_IP=%LAN_IP: =%
if "%LAN_IP%"=="" set LAN_IP=localhost

:: ---------------------------------------------------------------------------
:: Start backend in a new window
:: ---------------------------------------------------------------------------

echo [94m🔧 Starting backend on :8000...[0m
pushd "%SCRIPT_DIR%backend"
start "AI-DM Backend" /B cmd /c "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
popd

:: Give the backend a moment to bind
timeout /t 2 /nobreak >nul

:: ---------------------------------------------------------------------------
:: Print access URLs
:: ---------------------------------------------------------------------------

echo [92m🎨 Starting frontend on :5173...[0m
echo.
echo ========================================
echo   🌐 Local:   http://localhost:5173
echo   📱 LAN:     http://%LAN_IP%:5173
echo   🌍 Remote:  ngrok http 5173   (in another terminal)
echo ========================================
echo.
echo Close this window or press Ctrl-C to stop both servers.
echo.

:: ---------------------------------------------------------------------------
:: Start frontend (foreground)
:: ---------------------------------------------------------------------------

pushd "%SCRIPT_DIR%frontend"
pnpm dev --host 0.0.0.0
popd
