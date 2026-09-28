@echo off
setlocal
REM ---------------------------------------------------------------
REM  LegalEase - start the FastAPI backend on http://127.0.0.1:8000
REM ---------------------------------------------------------------
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment ".venv" was not found in %CD%
    echo.
    echo Create it and install the dependencies first:
    echo     python -m venv .venv
    echo     .venv\Scripts\activate.bat
    echo     pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Could not activate the virtual environment.
    pause
    exit /b 1
)

python -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FastAPI / Uvicorn are not installed in this environment.
    echo Run:  pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist ".env" (
    echo [WARNING] No .env file found. Copy .env.example to .env and add your GEMINI_API_KEY.
)

echo Starting LegalEase backend on http://127.0.0.1:8000  (Swagger: /docs)
echo Press CTRL+C to stop.
echo.
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

if errorlevel 1 (
    echo.
    echo [ERROR] The backend stopped with an error.
    echo If port 8000 is already in use, close the other program or change --port.
    pause
    exit /b 1
)
endlocal
