#!/bin/bash

echo "🍋 LEMON SQUEEZE WEB APP - SETUP & RUN 🍋"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"
echo ""

# Install requirements
echo "📦 Installing dependencies..."
pip3 install -r requirements_webapp.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully!"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo ""
echo "🚀 Starting Lemon Squeeze Web App..."
echo ""
echo "📱 Open your browser and go to: http://localhost:5000"
echo "🛑 Press Ctrl+C to stop the server"
echo ""
echo "=========================================="
echo ""

# Run the app
python3 lemon_squeeze_webapp.py
