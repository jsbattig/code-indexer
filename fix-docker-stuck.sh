#!/bin/bash

# Comprehensive Docker Recovery Script
# This script performs all the steps to recover from stuck Docker states

set -e  # Exit on any error

echo "🚨 Docker Recovery Script Starting..."
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to test if docker is responsive
test_docker_responsive() {
    echo -e "${BLUE}Testing docker responsiveness...${NC}"
    if timeout 5s docker ps >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Docker is responsive${NC}"
        return 0
    else
        echo -e "${RED}❌ Docker is not responsive${NC}"
        return 1
    fi
}

# Function to show current docker status
show_docker_status() {
    echo -e "${BLUE}Current docker status:${NC}"
    echo "Containers:"
    timeout 5s docker ps -a 2>/dev/null || echo "  - Cannot list containers"
    echo "Images:"
    timeout 5s docker images 2>/dev/null || echo "  - Cannot list images"
    echo "Networks:"
    timeout 5s docker network ls 2>/dev/null || echo "  - Cannot list networks"
    echo "Volumes:"
    timeout 5s docker volume ls 2>/dev/null || echo "  - Cannot list volumes"
    echo ""
}

# Function to force cleanup docker resources
cleanup_docker_resources() {
    echo -e "${YELLOW}🧹 Step 1: Cleaning up Docker resources...${NC}"
    
    # Stop all running containers
    echo "  Stopping all containers..."
    if timeout 10s docker ps -q 2>/dev/null | grep -q .; then
        timeout 30s docker stop $(docker ps -q) 2>/dev/null || echo "    No containers to stop or stop failed"
    else
        echo "    No running containers found"
    fi
    
    # Remove all containers
    echo "  Removing all containers..."
    if timeout 10s docker ps -aq 2>/dev/null | grep -q .; then
        timeout 30s docker rm -f $(docker ps -aq) 2>/dev/null || echo "    No containers to remove or removal failed"
    else
        echo "    No containers to remove"
    fi
    
    # Remove all custom networks (keep default ones)
    echo "  Cleaning up networks..."
    timeout 30s docker network prune -f 2>/dev/null || echo "    Network cleanup failed"
    
    # Remove unused volumes
    echo "  Cleaning up volumes..."
    timeout 30s docker volume prune -f 2>/dev/null || echo "    Volume cleanup failed"
    
    # Remove unused images
    echo "  Cleaning up images..."
    timeout 30s docker image prune -f 2>/dev/null || echo "    Image cleanup failed"
    
    # System prune for complete cleanup
    echo "  Running system prune..."
    timeout 30s docker system prune -f 2>/dev/null || echo "    System prune failed"
}

# Function to restart docker service
restart_docker_service() {
    echo -e "${YELLOW}🔄 Step 2: Restarting Docker service...${NC}"
    
    # Stop docker service
    echo "  Stopping docker service..."
    sudo systemctl stop docker.service 2>/dev/null || echo "    Service stop failed or not running"
    sudo systemctl stop docker.socket 2>/dev/null || echo "    Socket stop failed or not running"
    
    # Wait a moment
    sleep 2
    
    # Start docker service
    echo "  Starting docker service..."
    sudo systemctl start docker.service
    
    # Wait for service to be ready
    sleep 5
    
    echo "  Docker service restart completed"
}

# Function to reset docker completely
reset_docker_completely() {
    echo -e "${YELLOW}🔥 Step 3: Complete Docker reset...${NC}"
    
    # Stop all docker services
    echo "  Stopping all docker services..."
    sudo systemctl stop docker.service docker.socket containerd.service 2>/dev/null || true
    
    # Kill any remaining docker processes more aggressively
    echo "  Killing any remaining docker processes..."
    sudo pkill -f dockerd 2>/dev/null || echo "    No dockerd processes to kill"
    sudo pkill -f docker-proxy 2>/dev/null || echo "    No docker-proxy processes to kill"
    sudo pkill -f containerd 2>/dev/null || echo "    No containerd processes to kill"
    sudo pkill -9 dockerd 2>/dev/null || true
    sudo pkill -9 docker-proxy 2>/dev/null || true
    sudo pkill -9 containerd 2>/dev/null || true
    sudo pkill -9 containerd-shim 2>/dev/null || true
    sudo pkill -9 runc 2>/dev/null || true
    
    # Wait for processes to die
    sleep 5
    
    # Clean up runtime directories
    echo "  Cleaning runtime directories..."
    sudo rm -rf /var/run/docker/* 2>/dev/null || true
    sudo rm -rf /var/run/containerd/* 2>/dev/null || true
    sudo rm -rf /run/docker/* 2>/dev/null || true
    sudo rm -rf /tmp/docker-* 2>/dev/null || true
    
    # If docker is completely stuck, remove the entire storage (WARNING: loses all data)
    echo "  WARNING: Removing docker storage (complete reset - will lose all containers/images)..."
    read -p "  Continue with complete storage reset? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl stop docker.service docker.socket 2>/dev/null || true
        sudo rm -rf /var/lib/docker/* 2>/dev/null || true
        sudo rm -rf /var/lib/containerd/* 2>/dev/null || true
        echo "    Docker storage completely removed"
    else
        echo "    Skipping storage reset"
    fi
    
    # Reload systemd
    echo "  Reloading systemd..."
    sudo systemctl daemon-reload
    
    # Restart docker
    echo "  Restarting docker service..."
    sudo systemctl start docker.service
    sleep 5
}

# Function to clean system-wide resources
system_wide_cleanup() {
    echo -e "${YELLOW}🔧 Step 4: System-wide cleanup...${NC}"
    
    # Clean up any hanging mounts
    echo "  Cleaning up hanging mounts..."
    sudo umount -f /var/lib/docker/overlay2/*/merged 2>/dev/null || true
    sudo umount -f /var/lib/docker/containers/*/mounts/* 2>/dev/null || true
    sudo umount -f /var/lib/docker/overlay2/*/work 2>/dev/null || true
    
    # Clean up cgroup resources
    echo "  Cleaning cgroup resources..."
    sudo find /sys/fs/cgroup -name "*docker*" -type d 2>/dev/null | while read dir; do
        echo "    Removing cgroup: $dir"
        sudo rmdir "$dir" 2>/dev/null || true
    done
    
    # Clean up network namespaces more aggressively
    echo "  Cleaning network namespaces..."
    sudo ip netns list 2>/dev/null | grep -E "docker|bridge" | awk '{print $1}' | while read ns; do
        echo "    Removing network namespace: $ns"
        sudo ip netns delete "$ns" 2>/dev/null || true
    done
    
    # Clean up docker bridge networks
    echo "  Cleaning docker bridge networks..."
    sudo ip link show | grep docker | awk '{print $2}' | sed 's/:$//' | while read bridge; do
        echo "    Removing bridge: $bridge"
        sudo ip link delete "$bridge" 2>/dev/null || true
    done
    
    # Clean up iptables rules
    echo "  Cleaning iptables rules..."
    sudo iptables -t nat -F DOCKER 2>/dev/null || true
    sudo iptables -t filter -F DOCKER 2>/dev/null || true
    sudo iptables -t filter -F DOCKER-ISOLATION-STAGE-1 2>/dev/null || true
    sudo iptables -t filter -F DOCKER-ISOLATION-STAGE-2 2>/dev/null || true
    sudo iptables -t filter -F DOCKER-USER 2>/dev/null || true
    
    # Restart networking
    echo "  Restarting networking..."
    sudo systemctl restart NetworkManager 2>/dev/null || true
    
    # Reload systemd
    echo "  Reloading systemd..."
    sudo systemctl daemon-reload
    
    # Start docker again
    echo "  Starting docker service..."
    sudo systemctl start docker.service
    sleep 5
}

# Function to verify final state
verify_final_state() {
    echo -e "${BLUE}🔍 Final verification...${NC}"
    
    if test_docker_responsive; then
        echo -e "${GREEN}✅ Docker is now responsive!${NC}"
        show_docker_status
        return 0
    else
        echo -e "${RED}❌ Docker is still not responsive${NC}"
        return 1
    fi
}

# Main execution
echo "Starting Docker recovery process..."
echo ""

# Initial status check
echo -e "${BLUE}Initial state check:${NC}"
if test_docker_responsive; then
    echo -e "${GREEN}Docker appears to be working. Showing current status:${NC}"
    show_docker_status
    echo "If you're still having issues, continuing with cleanup..."
    echo ""
else
    echo "Docker is stuck. Beginning recovery process..."
    echo ""
fi

# Step 1: Clean up resources
cleanup_docker_resources
sleep 2

# Test after step 1
echo -e "${BLUE}Testing after resource cleanup...${NC}"
if test_docker_responsive; then
    echo -e "${GREEN}✅ Docker recovered after resource cleanup!${NC}"
    verify_final_state
    exit 0
fi

# Step 2: Restart service
restart_docker_service
sleep 3

# Test after step 2
echo -e "${BLUE}Testing after service restart...${NC}"
if test_docker_responsive; then
    echo -e "${GREEN}✅ Docker recovered after service restart!${NC}"
    verify_final_state
    exit 0
fi

# Step 3: Complete reset
reset_docker_completely
sleep 5

# Test after step 3
echo -e "${BLUE}Testing after complete reset...${NC}"
if test_docker_responsive; then
    echo -e "${GREEN}✅ Docker recovered after complete reset!${NC}"
    verify_final_state
    exit 0
fi

# Step 4: System-wide cleanup
echo -e "${RED}Docker still not responsive. Attempting system-wide cleanup...${NC}"
echo "This step requires sudo privileges."
system_wide_cleanup
sleep 5

# Final test
echo -e "${BLUE}Final test after system-wide cleanup...${NC}"
if test_docker_responsive; then
    echo -e "${GREEN}✅ Docker recovered after system-wide cleanup!${NC}"
    verify_final_state
    exit 0
else
    echo -e "${RED}❌ Docker recovery failed. Manual intervention may be required.${NC}"
    echo ""
    echo "Suggestions for manual recovery:"
    echo "1. Reboot the system"
    echo "2. Check system logs: sudo journalctl -u docker.service"
    echo "3. Check for disk space issues: df -h"
    echo "4. Check Docker daemon logs: sudo docker logs"
    echo "5. Consider reinstalling docker"
    echo "6. Check if docker daemon is enabled: sudo systemctl enable docker"
    exit 1
fi