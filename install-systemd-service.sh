#!/bin/bash
# Install Chatterbox API as systemd service
# Run with: sudo bash install-systemd-service.sh

set -e

echo "Installing Chatterbox TTS API as systemd service..."

# Install service file
sudo install -m 644 /tmp/chatterbox-api.service /etc/systemd/system/

echo "Service file installed to /etc/systemd/system/chatterbox-api.service"

# Reload systemd daemon
sudo systemctl daemon-reload
echo "Systemd daemon reloaded"

# Enable service to start on boot
sudo systemctl enable chatterbox-api.service
echo "Service enabled for auto-start on boot"

# Show status
sudo systemctl status chatterbox-api.service || true

echo ""
echo "Service installed successfully!"
echo ""
echo "Common commands:"
echo "  Start service:  sudo systemctl start chatterbox-api"
echo "  Stop service:   sudo systemctl stop chatterbox-api"
echo "  Restart:        sudo systemctl restart chatterbox-api"
echo "  Status:         sudo systemctl status chatterbox-api"
echo "  View logs:      sudo journalctl -u chatterbox-api -f"
echo ""
