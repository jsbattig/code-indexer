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
#   sudo ./deploy-server.sh [OPTIONS]
#
# Required:
#   --voyage-key KEY       VoyageAI API key for embeddings
#
# Optional:
#   --user USER            System user (default: current user)
#   --working-dir DIR      Code directory (default: current directory)
#   --issuer-url URL       Public URL for OAuth (default: http://localhost:8000)
#   --anthropic-key KEY    Anthropic API key (default: empty)
#   --port PORT            Server port (default: 8000)
#   --host HOST            Server host (default: 0.0.0.0)
#
# Prerequisites:
#   - Run as root or with sudo
#   - Python 3.9+ installed
#   - Code indexed in ~/.cidx-server/golden-repos
#

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to show usage
show_usage() {
    echo "Usage: sudo $0 [OPTIONS]"
    echo ""
    echo "Required:"
    echo "  --voyage-key KEY       VoyageAI API key for embeddings"
    echo ""
    echo "Optional:"
    echo "  --user USER            System user (default: current user)"
    echo "  --working-dir DIR      Code directory (default: current directory)"
    echo "  --issuer-url URL       Public URL for OAuth (default: http://localhost:8000)"
    echo "  --anthropic-key KEY    Anthropic API key (default: empty)"
    echo "  --port PORT            Server port (default: 8000)"
    echo "  --host HOST            Server host (default: 0.0.0.0)"
    echo ""
    echo "Examples:"
    echo "  Local development:"
    echo "    sudo $0 --voyage-key pa-xxx --user jsbattig --working-dir /home/jsbattig/Dev/code-indexer"
    echo ""
    echo "  Production with OAuth:"
    echo "    sudo $0 --voyage-key pa-xxx --anthropic-key sk-ant-xxx --user jsbattig \\"
    echo "      --working-dir /home/jsbattig/code-indexer --issuer-url https://linner.ddns.net:8383"
    exit 1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Get the actual user who ran sudo (not root)
ACTUAL_USER="${SUDO_USER:-$(whoami)}"
ACTUAL_USER_HOME=$(eval echo ~$ACTUAL_USER)

# Default values
DEPLOY_USER="$ACTUAL_USER"
WORKING_DIR="$(pwd)"
ISSUER_URL="http://localhost:8000"
ANTHROPIC_KEY=""
PORT="8000"
HOST="0.0.0.0"
VOYAGE_KEY=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --voyage-key)
            VOYAGE_KEY="$2"
            shift 2
            ;;
        --user)
            DEPLOY_USER="$2"
            shift 2
            ;;
        --working-dir)
            WORKING_DIR="$2"
            shift 2
            ;;
        --issuer-url)
            ISSUER_URL="$2"
            shift 2
            ;;
        --anthropic-key)
            ANTHROPIC_KEY="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            ;;
        *)
            echo -e "${RED}ERROR: Unknown option: $1${NC}"
            show_usage
            ;;
    esac
done

# Validate required parameters
if [ -z "$VOYAGE_KEY" ]; then
    echo -e "${RED}ERROR: --voyage-key is required${NC}"
    echo ""
    show_usage
fi

# Calculate user home directory for the deploy user (may differ from SUDO_USER)
DEPLOY_USER_HOME=$(eval echo ~$DEPLOY_USER)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CIDX Server Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Configuration:"
echo "  User:           $DEPLOY_USER"
echo "  Working Dir:    $WORKING_DIR"
echo "  User Home:      $DEPLOY_USER_HOME"
echo "  Issuer URL:     $ISSUER_URL"
echo "  Port:           $PORT"
echo "  Host:           $HOST"
echo "  Anthropic Key:  $([ -n "$ANTHROPIC_KEY" ] && echo 'Configured' || echo 'Not configured')"
echo "  Server Mode:    1 (hardcoded in template - CRITICAL for performance)"
echo ""

# Step 1: Copy systemd service file and replace placeholders
echo -e "${GREEN}Step 1: Installing systemd service file...${NC}"

SERVICE_FILE="/etc/systemd/system/cidx-server.service"
TEMPLATE_FILE="$(dirname "$0")/cidx-server.service"

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo -e "${RED}ERROR: Service template not found: $TEMPLATE_FILE${NC}"
    exit 1
fi

# Copy template
cp "$TEMPLATE_FILE" "$SERVICE_FILE"

# Replace all placeholders
# Note: CIDX_SERVER_MODE=1 is hardcoded in template (always needed for server mode)
sed -i "s|__USER__|$DEPLOY_USER|g" "$SERVICE_FILE"
sed -i "s|__WORKING_DIR__|$WORKING_DIR|g" "$SERVICE_FILE"
sed -i "s|__USER_HOME__|$DEPLOY_USER_HOME|g" "$SERVICE_FILE"
sed -i "s|__VOYAGE_API_KEY__|$VOYAGE_KEY|g" "$SERVICE_FILE"
sed -i "s|__ISSUER_URL__|$ISSUER_URL|g" "$SERVICE_FILE"
sed -i "s|__ANTHROPIC_API_KEY__|$ANTHROPIC_KEY|g" "$SERVICE_FILE"
sed -i "s|__HOST__|$HOST|g" "$SERVICE_FILE"
sed -i "s|__PORT__|$PORT|g" "$SERVICE_FILE"

echo -e "${GREEN}   Installed service file: $SERVICE_FILE${NC}"
echo -e "${GREEN}   Configured all environment variables and placeholders${NC}"

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

# Step 7: Display deployment summary
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
echo "Server endpoint:"
echo "  http://$HOST:$PORT"
echo ""
echo "Cache statistics endpoint (requires authentication):"
echo "  curl -H 'Authorization: Bearer TOKEN' http://localhost:$PORT/cache/stats"
echo ""
