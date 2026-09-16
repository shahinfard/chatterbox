@echo off
REM Startup script for Chatterbox TTS OpenAI API Server (Windows)

echo ================================================
echo Chatterbox TTS - OpenAI Compatible API Server
echo ================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

echo Starting API server...
echo Server will be available at: http://localhost:5005
echo Press Ctrl+C to stop the server
echo.

REM Start the server
REM If a virtual environment does not exist, create it and install API requirements
if not exist .venv\Scripts\activate.bat (
    echo Creating virtual environment in .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Upgrading pip in the venv and installing API dependencies using venv python...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    if exist api_requirements.txt (
        .venv\Scripts\python.exe -m pip install -r api_requirements.txt
    ) else (
        echo WARNING: api_requirements.txt not found; skipping pip install.
    )
) else (
    echo Virtual environment already exists.
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check for PyTorch (not auto-installed due to platform/CUDA choices)
python tools\check_torch.py
if errorlevel 1 (
    echo.
    echo.
    echo WARNING: PyTorch ^(torch^) not found in the virtual environment.
    echo Please install PyTorch appropriate for your platform/CUDA from https://pytorch.org/get-started/locally/
    echo For a CPU-only quick test you can run: pip install torch --index-url https://download.pytorch.org/whl/cpu
    echo.
)

python openai_api_server.py

pause
