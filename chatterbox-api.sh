#!/bin/bash
# Chatterbox TTS API Server Startup Script
# This script activates the venv and runs the API server on GPU 1 (RTX 4090)

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pin to GPU 1 (RTX 5090)
export CUDA_VISIBLE_DEVICES=0

# Activate virtual environment
source "${SCRIPT_DIR}/venv/bin/activate"

# Run the API server
exec python "${SCRIPT_DIR}/openai_api_server.py"
