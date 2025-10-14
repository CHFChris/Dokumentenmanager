@echo off
setlocal ENABLEDELAYEDEXPANSION

rem ---- Root & Ports
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PORT_BACKEND=8000"
set "PORT_FRONTEND=5173"

echo =============================================
echo  Dokumentenmanager Starter (Backend + Frontend)
echo  Root: %ROOT%
echo  Backend-Port: %PORT_BACKEND%
echo  Frontend-Port: %PORT_FRONTEND%
echo =============================================
echo.

rem ---- venv finden
set "VENV_ACT="
if exist ".venv\Scripts\activate.bat" set "VENV_ACT=.venv\Scripts\activate.bat"
if exist "venv\Scripts\activate.bat"  set "VENV_ACT=venv\Scripts\activate.bat"

rem ---- Check
if not exist "app\main.py" (
  echo [FEHLER] app\main.py nicht gefunden. Bist du im richtigen Projektordner?
  pause
  goto :eof
)

rem ---- Backend starten (neues Fenster)
if defined VENV_ACT (
  start "Backend (FastAPI :%PORT_BACKEND%)" cmd /k pushd "%ROOT%" ^& call "%VENV_ACT%" ^& python -m uvicorn app.main:app --reload --host 127.0.0.1 --port %PORT_BACKEND% --reload-dir app --reload-exclude=.venv --reload-exclude=venv --reload-exclude=dokumentenmanager_frontend\node_modules
) else (
  echo [HINWEIS] Keine venv gefunden. Starte mit globalem Python...
  start "Backend (FastAPI :%PORT_BACKEND%)" cmd /k pushd "%ROOT%" ^& python -m uvicorn app.main:app --reload --host 127.0.0.1 --port %PORT_BACKEND% --reload-dir app --reload-exclude=.venv --reload-exclude=venv --reload-exclude=dokumentenmanager_frontend\node_modules
)

rem ---- Frontend starten (neues Fenster)
if exist "dokumentenmanager_frontend" (
  if not exist "dokumentenmanager_frontend\node_modules" (
    echo [INFO] Installiere Frontend-Abhaengigkeiten (einmalig)...
    pushd "dokumentenmanager_frontend"
    call npm ci || call npm install
    popd
  )
  start "Frontend (Vite :%PORT_FRONTEND%)" cmd /k cd /d "%ROOT%dokumentenmanager_frontend" ^& npm run dev -- --port %PORT_FRONTEND%
) else (
  echo [FEHLER] Frontend-Ordner "dokumentenmanager_frontend" nicht gefunden.
)

echo.
echo [OK] Backend:  http://localhost:%PORT_BACKEND%
echo [OK] Frontend: http://localhost:%PORT_FRONTEND%
echo.
pause
endlocal
