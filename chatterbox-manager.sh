#!/bin/bash
# Unified script to manage the chatterbox-api service
# Usage: ./chatterbox-manager.sh {start|stop|restart|status}

SERVICE_NAME="chatterbox-api"

case "$1" in
    start)
        echo "Starting $SERVICE_NAME service..."
        sudo systemctl start $SERVICE_NAME
        echo "$SERVICE_NAME service started."
        ;;
    stop)
        echo "Stopping $SERVICE_NAME service..."
        sudo systemctl stop $SERVICE_NAME
        echo "$SERVICE_NAME service stopped."
        ;;
    restart)
        echo "Restarting $SERVICE_NAME service..."
        sudo systemctl restart $SERVICE_NAME
        echo "$SERVICE_NAME service restarted."
        ;;
    status)
        echo "Checking status of $SERVICE_NAME service..."
        sudo systemctl status $SERVICE_NAME
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo "  start   - Start the chatterbox-api service"
        echo "  stop    - Stop the chatterbox-api service" 
        echo "  restart - Restart the chatterbox-api service"
        echo "  status  - Check the status of the chatterbox-api service"
        exit 1
        ;;
esac