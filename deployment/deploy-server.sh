#!/bin/bash
#
# CIDX Server Deployment Script
#
# This script deploys the CIDX server to the local system using systemd.
#
# The HNSW index cache (Story #526) is automatically initialized when the server starts,
# providing 100-1800x query performance improvements.
#
# Usage:
#   sudo ./deploy-server.sh [voyage_api_key]
#
# Prerequisites:
#   - Run as root or with sudo
#   - VOYAGE_API_KEY provided as argument or in environment
#   - Python 3.9+ installed
#   - Code indexed in ~/.cidx-server/golden-repos
#

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CIDX Server Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Get VOYAGE_API_KEY from argument or environment
VOYAGE_API_KEY="${1:-$VOYAGE_API_KEY}"

if [ -z "$VOYAGE_API_KEY" ]; then
    echo -e "${YELLOW}WARNING: No VOYAGE_API_KEY provided${NC}"
    echo "Server will fail to start without a valid API key."
    echo "You can provide it via:"
    echo "  1. Command line: sudo ./deploy-server.sh YOUR_API_KEY"
    echo "  2. Environment: export VOYAGE_API_KEY=YOUR_KEY && sudo -E ./deploy-server.sh"
    echo "  3. Manually edit /etc/systemd/system/cidx-server.service after installation"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 1: Copy systemd service file
echo -e "${GREEN}Step 1: Installing systemd service file...${NC}"

SERVICE_FILE="/etc/systemd/system/cidx-server.service"
TEMPLATE_FILE="$(dirname "$0")/cidx-server.service"

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}ERROR: Service template not found: $TEMPLATE_FILE${NC}"
    exit 1
fi

# Copy template and replace API key placeholder
cp "$TEMPLATE_FILE" "$SERVICE_FILE"

if [ -n "$VOYAGE_API_KEY" ]; then
    sed -i "s/your_voyage_api_key_here/$VOYAGE_API_KEY/" "$SERVICE_FILE"
    echo -e "${GREEN}   Configured VOYAGE_API_KEY in service file${NC}"
fi

echo -e "${GREEN}   Installed service file: $SERVICE_FILE${NC}"

# Step 2: Reload systemd configuration
echo -e "${GREEN}Step 2: Reloading systemd configuration...${NC}"
systemctl daemon-reload
echo -e "${GREEN}   Systemd configuration reloaded${NC}"

# Step 3: Enable service to start on boot
echo -e "${GREEN}Step 3: Enabling cidx-server service...${NC}"
systemctl enable cidx-server
echo -e "${GREEN}   Service enabled (will start on boot)${NC}"

# Step 4: Restart service
echo -e "${GREEN}Step 4: Restarting cidx-server service...${NC}"
systemctl restart cidx-server
echo -e "${GREEN}   Service restarted${NC}"

# Step 5: Wait for service to start
echo -e "${GREEN}Step 5: Waiting for service to start...${NC}"
sleep 3

# Step 6: Verify service status
echo -e "${GREEN}Step 6: Verifying service status...${NC}"
if systemctl is-active --quiet cidx-server; then
    echo -e "${GREEN}   Service is ACTIVE${NC}"
else
    echo -e "${RED}   ERROR: Service failed to start${NC}"
    echo -e "${YELLOW}   Service status:${NC}"
    systemctl status cidx-server --no-pager
    exit 1
fi

fi

# Check environment variables
echo ""

# Step 9: Display service logs
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Service status:"
systemctl status cidx-server --no-pager --lines=10
echo ""
echo "Useful commands:"
echo "  View logs:           sudo journalctl -u cidx-server -f"
echo "  Stop service:        sudo systemctl stop cidx-server"
echo "  Start service:       sudo systemctl start cidx-server"
echo "  Restart service:     sudo systemctl restart cidx-server"
echo "  Service status:      sudo systemctl status cidx-server"
echo "  Disable service:     sudo systemctl disable cidx-server"
echo ""
echo "Cache statistics endpoint (requires authentication):"
echo "  curl -H 'Authorization: Bearer TOKEN' http://localhost:8000/cache/stats"
echo ""
