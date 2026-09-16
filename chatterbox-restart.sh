#!/bin/bash
# Script to restart the chatterbox-api service

echo "Restarting chatterbox-api service..."
sudo systemctl restart chatterbox-api
echo "Chatterbox-api service restarted."