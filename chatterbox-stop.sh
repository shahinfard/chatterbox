#!/bin/bash
# Script to stop the chatterbox-api service

echo "Stopping chatterbox-api service..."
sudo systemctl stop chatterbox-api
echo "Chatterbox-api service stopped."