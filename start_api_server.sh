#!/bin/bash
# Startup script for Chatterbox TTS OpenAI API Server (Linux/Mac)

echo "================================================"
echo "Chatterbox TTS - OpenAI Compatible API Server"
echo "================================================"
echo ""

# Check if Python is available
if ! command -v python &> /dev/null; then
    if ! command -v python3 &> /dev/null; then
        echo "ERROR: Python not found. Please install Python 3.8+"
        exit 1
    else
        PYTHON=python3
    fi
else
    PYTHON=python
fi

echo "Starting API server..."
echo "Server will be available at: http://localhost:5005"
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
$PYTHON openai_api_server.py
