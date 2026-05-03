@echo off
echo ========================================
echo   Frontend Dual Server Launcher
echo ========================================
echo.
echo This will start both:
echo   1. API Server (port 3001)
echo   2. Frontend Dev Server (port 5173)
echo.
echo Press Ctrl+C to stop both servers
echo ========================================
echo.

start "API Server" cmd /k "npm run server"
timeout /t 2 /nobreak >nul
start "Frontend Server" cmd /k "npm run dev"

echo.
echo Both servers are starting...
echo.
echo API Server: http://localhost:3001
echo Frontend: http://localhost:5173
echo.
echo Close this window or press any key to exit launcher
echo (Note: This will NOT stop the servers!)
pause >nul
