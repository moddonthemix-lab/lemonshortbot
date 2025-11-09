@echo off
echo ========================================
echo 🍋 LEMON SQUEEZE WEB APP - SETUP ^& RUN 🍋
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed. Please install Python 3.7 or higher.
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Install requirements
echo 📦 Installing dependencies...
pip install -r requirements_webapp.txt

if %errorlevel% neq 0 (
    echo ❌ Failed to install dependencies
    pause
    exit /b 1
)

echo ✅ Dependencies installed successfully!
echo.

echo 🚀 Starting Lemon Squeeze Web App...
echo.
echo 📱 Open your browser and go to: http://localhost:5000
echo 🛑 Press Ctrl+C to stop the server
echo.
echo ========================================
echo.

REM Run the app
python lemon_squeeze_webapp.py

pause
