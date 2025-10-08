@echo off
setlocal ENABLEDELAYEDEXPANSION

echo =============================================
echo  Dokumentenmanager Starter (Backend + Frontend)
echo =============================================
echo.

cd /d "%~dp0"

rem --- Backend starten (neues Fenster)
if exist ".venv\Scripts\activate.bat" (
    start "Backend (FastAPI)" cmd /k "call .venv\Scripts\activate && uvicorn app.main:app --reload --port 5173"
) else (
    start "Backend (FastAPI)" cmd /k "uvicorn app.main:app --reload --port 5173"
)

rem --- Frontend starten (neues Fenster)
if exist "dokumentenmanager_frontend" (
    start "Frontend (Vite)" cmd /k "cd /d dokumentenmanager_frontend && npm install && npm run dev"
) else (
    echo [FEHLER] Frontend-Ordner nicht gefunden.
    pause
)

pause
endlocal
