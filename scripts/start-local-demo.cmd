@echo off
setlocal
cd /d "%~dp0.."

if not exist "frontend\node_modules" (
  where pnpm >nul 2>nul
  if errorlevel 1 (
    echo pnpm is required for first-time setup. Install Node.js and run: npm install -g pnpm
    pause
    exit /b 1
  )
  echo Installing frontend dependencies...
  call pnpm --dir frontend install --frozen-lockfile --ignore-scripts
  if errorlevel 1 goto :failed
)

if not exist "frontend\dist\index.html" (
  where pnpm >nul 2>nul
  if errorlevel 1 (
    echo pnpm is required to build the frontend. Run: npm install -g pnpm
    pause
    exit /b 1
  )
  echo Building Sentinel Tool...
  call pnpm --dir frontend run build
  if errorlevel 1 goto :failed
)

echo Sentinel Tool demo: http://127.0.0.1:4173/dashboard
echo Keep this window open while using Sentinel.
call "frontend\node_modules\.bin\vite.cmd" preview --host 127.0.0.1 --port 4173 --open /dashboard
exit /b %errorlevel%

:failed
echo Sentinel Tool could not be started. Review the error above.
pause
exit /b 1
