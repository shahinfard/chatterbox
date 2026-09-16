@echo off
REM Setup and install PyTorch into the repository .venv on Windows

echo ================================================
echo Setup venv and install PyTorch helper
echo ================================================

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Create venv if missing
if not exist .venv\Scripts\activate.bat (
    echo Creating virtual environment in .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

if exist api_requirements.txt (
    echo Installing API requirements from api_requirements.txt...
    python -m pip install -r api_requirements.txt
)

echo Running installer to detect CUDA and install appropriate PyTorch build...
python tools\install_torch.py %*

echo Done. If PyTorch installed successfully, you can run:
echo    .\start_api_server.bat

pause
