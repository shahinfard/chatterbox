# Chatterbox Turbo TTS - Linux Setup Guide

This guide covers the complete setup of Chatterbox Turbo TTS with the OpenAI-compatible API server on Linux, pinned to a specific GPU.

## System Requirements

- Python 3.10+ (using 3.12.12)
- NVIDIA GPU with CUDA support (RTX 4090 or RTX 5090)
- ~2GB disk space for models
- 24GB+ VRAM (RTX 4090/5090 recommended)

## What's Installed

1. **Chatterbox Turbo TTS** - Latest open-source TTS model from Resemble AI
2. **OpenAI-Compatible API Server** - Drop-in replacement for OpenAI TTS API
3. **Python Virtual Environment** - Isolated Python 3.12.12 environment with pyenv
4. **Systemd Service** - Auto-start on boot and restart on failure

## Project Structure

```
/mnt/ai-storage/github/chatterbox-streaming/
├── venv/                           # Python virtual environment
├── src/chatterbox/                 # Chatterbox source code
│   ├── tts.py                      # Standard TTS module
│   ├── tts_turbo.py                # New Turbo TTS module (faster)
│   └── models/                     # Model implementations
├── openai_api_server.py            # OpenAI-compatible API server
├── api_requirements.txt            # API-specific dependencies
├── chatterbox-api.sh               # Systemd startup script
├── install-systemd-service.sh      # Installation script for systemd
├── .python-version                 # PyEnv version marker
└── API_SERVER_README.md            # Full API documentation
```

## GPU Configuration

This setup pins the service to **GPU 1 (RTX 4090)** via `CUDA_VISIBLE_DEVICES=1`.

### Check Your GPUs

```bash
nvidia-smi --list-gpus
```

Example output:
```
GPU 0: NVIDIA GeForce RTX 5090
GPU 1: NVIDIA GeForce RTX 4090
```

To change which GPU to use, edit the `chatterbox-api.sh` file and change:
```bash
export CUDA_VISIBLE_DEVICES=1  # Change to 0 for RTX 5090, etc
```

## Virtual Environment

The Python environment is managed by **pyenv** and uses Python 3.12.12.

### Activate the Virtual Environment

```bash
cd /mnt/ai-storage/github/chatterbox-streaming
source venv/bin/activate

# Verify
python --version  # Should be 3.12.12
```

### Install Additional Packages

```bash
source venv/bin/activate
pip install -e .  # Install Chatterbox
pip install -r api_requirements.txt  # Install API dependencies
```

## Manual Testing

Before setting up as a service, test the API server:

```bash
# Terminal 1: Start the server
cd /mnt/ai-storage/github/chatterbox-streaming
source venv/bin/activate
export CUDA_VISIBLE_DEVICES=1  # Pin to RTX 4090
python openai_api_server.py
```

The server will start loading models (takes ~20-30 seconds on first run).

```bash
# Terminal 2: Test the API
curl http://localhost:5005/health

# Expected response:
# {"status":"healthy","model_loaded":true,"device":"cuda"}
```

## Systemd Service Setup

### Step 1: Verify Prerequisites

```bash
# Check if service file exists
ls -l /tmp/chatterbox-api.service

# Check if startup script is executable
ls -l /mnt/ai-storage/github/chatterbox-streaming/chatterbox-api.sh

# Check if installer script exists
ls -l /mnt/ai-storage/github/chatterbox-streaming/install-systemd-service.sh
```

### Step 2: Install the Service

Run the installation script with sudo:

```bash
sudo bash /mnt/ai-storage/github/chatterbox-streaming/install-systemd-service.sh
```

This will:
1. Copy the service file to `/etc/systemd/system/`
2. Reload the systemd daemon
3. Enable the service for auto-start on boot
4. Show the service status

### Step 3: Start the Service

```bash
# Start the service
sudo systemctl start chatterbox-api

# Check status
sudo systemctl status chatterbox-api

# View logs (live tail)
sudo journalctl -u chatterbox-api -f
```

Wait 20-30 seconds for the model to load. You'll see "Server ready to accept requests" in logs.

### Step 4: Test the Running Service

```bash
curl http://localhost:5005/health

# Expected response:
# {"status":"healthy","model_loaded":true,"device":"cuda"}

# Test TTS generation
curl http://localhost:5005/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model":"tts-1",
    "input":"Hello! This is a test of the Chatterbox API.",
    "voice":"her",
    "response_format":"mp3"
  }' \
  -o test_output.mp3

# Play the output
ffplay test_output.mp3
```

## Service Management

### View Service Status

```bash
sudo systemctl status chatterbox-api

# Detailed output with logs
sudo systemctl status -l chatterbox-api

# Check if service is running
sudo systemctl is-active chatterbox-api
```

### View Logs

```bash
# Recent logs (last 50 lines)
sudo journalctl -u chatterbox-api -n 50

# Live tail (like tail -f)
sudo journalctl -u chatterbox-api -f

# Last 5 minutes
sudo journalctl -u chatterbox-api --since "5 minutes ago"

# Pretty format
sudo journalctl -u chatterbox-api -o short-iso
```

### Control the Service

```bash
# Start
sudo systemctl start chatterbox-api

# Stop
sudo systemctl stop chatterbox-api

# Restart
sudo systemctl restart chatterbox-api

# Enable on boot (default - already done)
sudo systemctl enable chatterbox-api

# Disable on boot
sudo systemctl disable chatterbox-api

# View enabled status
sudo systemctl is-enabled chatterbox-api
```

## Configuration

### Change GPU

Edit `chatterbox-api.sh`:

```bash
nano /mnt/ai-storage/github/chatterbox-streaming/chatterbox-api.sh
```

Change:
```bash
export CUDA_VISIBLE_DEVICES=1  # 0 for GPU 0, 1 for GPU 1, etc
```

Then restart the service:
```bash
sudo systemctl restart chatterbox-api
```

### Change Server Port

Edit `openai_api_server.py`:

```bash
nano /mnt/ai-storage/github/chatterbox-streaming/openai_api_server.py
```

Find and change:
```python
class ServerConfig:
    PORT = 5005  # Change this to desired port
```

Then restart:
```bash
sudo systemctl restart chatterbox-api
```

### Change Server Host/Bind Address

Similarly in `ServerConfig`:
```python
HOST = "0.0.0.0"  # 127.0.0.1 for localhost only, 0.0.0.0 for all interfaces
```

## API Endpoints

Once running, access:

- **Health Check**: `GET http://localhost:5005/health`
- **List Models**: `GET http://localhost:5005/v1/models`
- **List Voices**: `GET http://localhost:5005/v1/audio/voices`
- **Generate Speech**: `POST http://localhost:5005/v1/audio/speech`
- **API Docs**: `http://localhost:5005/docs` (Swagger UI)

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status chatterbox-api

# View recent errors
sudo journalctl -u chatterbox-api -n 100

# Try starting manually to see errors
cd /mnt/ai-storage/github/chatterbox-streaming
source venv/bin/activate
bash chatterbox-api.sh
```

### "Port already in use"

```bash
# Find what's using port 5005
sudo lsof -i :5005

# Kill the process if needed
sudo kill -9 <PID>

# Or change the port in openai_api_server.py
```

### CUDA Out of Memory

The model requires significant VRAM. If you get OOM errors:

1. Check GPU memory:
   ```bash
   nvidia-smi
   ```

2. Close other GPU processes

3. Restart the service:
   ```bash
   sudo systemctl restart chatterbox-api
   ```

### "Voice sample not found"

Add voice samples to the project root and update `ServerConfig.VOICE_PRESETS` in `openai_api_server.py`.

## Integration with OpenWebUI

1. Open OpenWebUI settings
2. Go to **Settings** → **Audio**
3. Set **TTS Engine** to **OpenAI**
4. Set **API Base URL** to `http://localhost:5005/v1`
5. Set **API Key** to anything (not required)
6. Select voice and test

## Git Workflow

### View Recent Changes

```bash
cd /mnt/ai-storage/github/chatterbox-streaming

# Current branch
git branch -v

# See all branches and remotes
git branch -a

# Recent commits
git log --oneline -10
```

### Working with Branches

```bash
# Switch to master (latest upstream)
git checkout master

# Switch to API integration branch
git checkout feature/openai-api-integration

# Create a new branch
git checkout -b feature/new-feature

# Merge changes
git merge feature/new-feature

# Push to your fork
git push origin feature/new-feature
```

### Push Changes to Your Fork

```bash
git push origin master
git push origin feature/openai-api-integration
```

## Performance Notes

**RTX 4090 Performance**:
- First chunk latency: ~0.47s
- Real-time factor (RTF): ~0.50
- Audio generation is faster than real-time

**Model Information**:
- Uses Chatterbox Turbo (350M parameters)
- Supports streaming inference
- Voice cloning with 24kHz sample rate

## Next Steps

1. Test with real applications (OpenWebUI, etc.)
2. Configure voice samples for different personas
3. Monitor service logs for performance metrics
4. Consider reverse proxy (nginx) for production
5. Set up monitoring/alerting if needed

## Support & Resources

- **Chatterbox Repo**: https://github.com/resemble-ai/chatterbox
- **Your Fork**: https://github.com/shahinfard/chatterbox
- **API Documentation**: See API_SERVER_README.md
- **FastAPI Docs**: http://localhost:5005/docs (when running)

## Quick Reference

```bash
# Activate venv
cd /mnt/ai-storage/github/chatterbox-streaming && source venv/bin/activate

# Start service
sudo systemctl start chatterbox-api

# Stop service
sudo systemctl stop chatterbox-api

# View logs
sudo journalctl -u chatterbox-api -f

# Test API
curl http://localhost:5005/health
```
