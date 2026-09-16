#!/bin/bash
# Chatterbox TTS API Server Startup Script
# This script activates the venv and runs the API server
# GPU selection is handled in openai_api_server.py (cuda:1 = RTX 5090)

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
source "${SCRIPT_DIR}/venv/bin/activate"

# Run the API server
exec python "${SCRIPT_DIR}/openai_api_server.py"
