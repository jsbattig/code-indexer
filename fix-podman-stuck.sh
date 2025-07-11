#!/bin/bash

# Comprehensive Podman Recovery Script
# This script performs all the steps we've used to recover from stuck Podman states

set -e  # Exit on any error

echo "🚨 Podman Recovery Script Starting..."
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to test if podman is responsive
test_podman_responsive() {
    echo -e "${BLUE}Testing podman responsiveness...${NC}"
    if timeout 5s podman ps >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Podman is responsive${NC}"
        return 0
    else
        echo -e "${RED}❌ Podman is not responsive${NC}"
        return 1
    fi
}

# Function to show current podman status
show_podman_status() {
    echo -e "${BLUE}Current podman status:${NC}"
    echo "Containers:"
    timeout 5s podman ps -a 2>/dev/null || echo "  - Cannot list containers"
    echo "Pods:"
    timeout 5s podman pod ls 2>/dev/null || echo "  - Cannot list pods"
    echo "Networks:"
    timeout 5s podman network ls 2>/dev/null || echo "  - Cannot list networks"
    echo "Volumes:"
    timeout 5s podman volume ls 2>/dev/null || echo "  - Cannot list volumes"
    echo ""
}

# Function to force cleanup podman resources
cleanup_podman_resources() {
    echo -e "${YELLOW}🧹 Step 1: Cleaning up Podman resources...${NC}"
    
    # Stop all running containers
    echo "  Stopping all containers..."
    if timeout 10s podman ps -q 2>/dev/null; then
        timeout 30s podman stop $(podman ps -q) 2>/dev/null || echo "    No containers to stop or stop failed"
    fi
    
    # Remove all containers
    echo "  Removing all containers..."
    if timeout 10s podman ps -aq 2>/dev/null; then
        timeout 30s podman rm -f $(podman ps -aq) 2>/dev/null || echo "    No containers to remove or removal failed"
    fi
    
    # Stop and remove all pods
    echo "  Cleaning up pods..."
    if timeout 10s podman pod ls -q 2>/dev/null; then
        timeout 30s podman pod stop $(podman pod ls -q) 2>/dev/null || echo "    No pods to stop or stop failed"
        timeout 30s podman pod rm -f $(podman pod ls -q) 2>/dev/null || echo "    No pods to remove or removal failed"
    fi
    
    # Remove networks (except default)
    echo "  Cleaning up networks..."
    timeout 30s podman network prune -f 2>/dev/null || echo "    Network cleanup failed"
    
    # Remove volumes
    echo "  Cleaning up volumes..."
    timeout 30s podman volume prune -f 2>/dev/null || echo "    Volume cleanup failed"
}

# Function to restart podman service
restart_podman_service() {
    echo -e "${YELLOW}🔄 Step 2: Restarting Podman service...${NC}"
    
    # Stop podman socket
    echo "  Stopping podman socket..."
    systemctl --user stop podman.socket 2>/dev/null || echo "    Socket stop failed or not running"
    
    # Stop podman service
    echo "  Stopping podman service..."
    systemctl --user stop podman.service 2>/dev/null || echo "    Service stop failed or not running"
    
    # Wait a moment
    sleep 2
    
    # Start podman socket
    echo "  Starting podman socket..."
    systemctl --user start podman.socket
    
    # Wait for socket to be ready
    sleep 3
    
    echo "  Podman service restart completed"
}

# Function to reset podman completely
reset_podman_completely() {
    echo -e "${YELLOW}🔥 Step 3: Complete Podman reset...${NC}"
    
    # Stop all user services
    echo "  Stopping all podman user services..."
    systemctl --user stop podman.socket podman.service 2>/dev/null || true
    
    # Kill any remaining podman processes more aggressively
    echo "  Killing any remaining podman processes..."
    pkill -f podman 2>/dev/null || echo "    No podman processes to kill"
    pkill -9 podman 2>/dev/null || true
    pkill -9 conmon 2>/dev/null || true
    pkill -9 crun 2>/dev/null || true
    pkill -9 runc 2>/dev/null || true
    
    # Wait for processes to die
    sleep 5
    
    # Clean up runtime directory
    echo "  Cleaning runtime directories..."
    rm -rf ~/.local/share/containers/storage/tmp/* 2>/dev/null || true
    rm -rf /run/user/$(id -u)/containers/* 2>/dev/null || true
    rm -rf /run/user/$(id -u)/libpod/* 2>/dev/null || true
    rm -rf /tmp/podman-run-$(id -u)/ 2>/dev/null || true
    rm -rf /tmp/containers-user-$(id -u)/ 2>/dev/null || true
    
    # If podman is completely stuck, remove the entire storage
    echo "  Removing podman storage (complete reset)..."
    rm -rf ~/.local/share/containers/ 2>/dev/null || true
    rm -rf ~/.config/containers/ 2>/dev/null || true
    
    # Reset podman system (might fail if podman is stuck)
    echo "  Attempting podman system reset..."
    timeout 10s podman system reset --force 2>/dev/null || echo "    System reset failed - proceeding with manual cleanup"
    
    # Reinitialize podman
    echo "  Reinitializing podman..."
    systemctl --user daemon-reload
    
    # Migrate podman to create fresh directories
    echo "  Running podman system migrate..."
    podman system migrate 2>/dev/null || echo "    Migration failed - will retry after service start"
    
    # Restart podman
    echo "  Restarting podman service..."
    systemctl --user start podman.socket
    sleep 5
    
    # Try migration again after service start
    podman system migrate 2>/dev/null || true
}

# Function to clean system-wide if needed (requires sudo)
system_wide_cleanup() {
    echo -e "${YELLOW}🔧 Step 4: System-wide cleanup (requires sudo)...${NC}"
    
    # Clean up any system-wide container resources
    echo "  Cleaning system-wide container resources..."
    sudo systemctl stop podman.socket podman.service 2>/dev/null || true
    sudo pkill -f podman 2>/dev/null || echo "    No system podman processes to kill"
    sudo pkill -9 podman 2>/dev/null || true
    sudo pkill -9 conmon 2>/dev/null || true
    
    # Clean up any hanging mounts
    echo "  Cleaning up hanging mounts..."
    sudo umount -f /run/user/$(id -u)/netns/* 2>/dev/null || true
    sudo umount -f /var/lib/containers/storage/overlay/* 2>/dev/null || true
    sudo umount -f /run/containers/storage/* 2>/dev/null || true
    
    # Remove system-wide podman directories if they exist
    echo "  Removing system podman directories..."
    sudo rm -rf /var/lib/containers/ 2>/dev/null || true
    sudo rm -rf /run/containers/ 2>/dev/null || true
    sudo rm -rf /run/libpod/ 2>/dev/null || true
    
    # Clean up cgroup resources
    echo "  Cleaning cgroup resources..."
    sudo find /sys/fs/cgroup -name "*podman*" -type d 2>/dev/null | while read dir; do
        echo "    Removing cgroup: $dir"
        sudo rmdir "$dir" 2>/dev/null || true
    done
    
    # Clean up network namespaces more aggressively
    echo "  Cleaning network namespaces..."
    sudo ip netns list 2>/dev/null | grep -E "netns|cni|podman" | awk '{print $1}' | while read ns; do
        echo "    Removing network namespace: $ns"
        sudo ip netns delete "$ns" 2>/dev/null || true
    done
    
    # Clean up any CNI networks
    echo "  Cleaning CNI networks..."
    sudo rm -rf /var/lib/cni/ 2>/dev/null || true
    sudo rm -rf /etc/cni/net.d/ 2>/dev/null || true
    
    # Restart networking
    echo "  Restarting networking..."
    sudo systemctl restart NetworkManager 2>/dev/null || true
    
    # Reload systemd
    echo "  Reloading systemd..."
    systemctl --user daemon-reload
    sudo systemctl daemon-reload
    
    # Start user podman again
    echo "  Starting user podman service..."
    systemctl --user start podman.socket
    sleep 5
}

# Function to verify final state
verify_final_state() {
    echo -e "${BLUE}🔍 Final verification...${NC}"
    
    if test_podman_responsive; then
        echo -e "${GREEN}✅ Podman is now responsive!${NC}"
        show_podman_status
        return 0
    else
        echo -e "${RED}❌ Podman is still not responsive${NC}"
        return 1
    fi
}

# Main execution
echo "Starting Podman recovery process..."
echo ""

# Initial status check
echo -e "${BLUE}Initial state check:${NC}"
if test_podman_responsive; then
    echo -e "${GREEN}Podman appears to be working. Showing current status:${NC}"
    show_podman_status
    echo "If you're still having issues, continuing with cleanup..."
    echo ""
else
    echo "Podman is stuck. Beginning recovery process..."
    echo ""
fi

# Step 1: Clean up resources
cleanup_podman_resources
sleep 2

# Test after step 1
echo -e "${BLUE}Testing after resource cleanup...${NC}"
if test_podman_responsive; then
    echo -e "${GREEN}✅ Podman recovered after resource cleanup!${NC}"
    verify_final_state
    exit 0
fi

# Step 2: Restart service
restart_podman_service
sleep 3

# Test after step 2
echo -e "${BLUE}Testing after service restart...${NC}"
if test_podman_responsive; then
    echo -e "${GREEN}✅ Podman recovered after service restart!${NC}"
    verify_final_state
    exit 0
fi

# Step 3: Complete reset
reset_podman_completely
sleep 5

# Test after step 3
echo -e "${BLUE}Testing after complete reset...${NC}"
if test_podman_responsive; then
    echo -e "${GREEN}✅ Podman recovered after complete reset!${NC}"
    verify_final_state
    exit 0
fi

# Step 4: System-wide cleanup (requires sudo)
echo -e "${RED}Podman still not responsive. Attempting system-wide cleanup...${NC}"
echo "This step requires sudo privileges."
system_wide_cleanup
sleep 5

# Final test
echo -e "${BLUE}Final test after system-wide cleanup...${NC}"
if test_podman_responsive; then
    echo -e "${GREEN}✅ Podman recovered after system-wide cleanup!${NC}"
    verify_final_state
    exit 0
else
    echo -e "${RED}❌ Podman recovery failed. Manual intervention may be required.${NC}"
    echo ""
    echo "Suggestions for manual recovery:"
    echo "1. Reboot the system"
    echo "2. Check system logs: journalctl --user -u podman.service"
    echo "3. Check for disk space issues: df -h"
    echo "4. Consider reinstalling podman"
    exit 1
fi