#!/bin/bash

echo "🔍 Podman Troubleshooting Script"
echo "================================"

# 1. Check podman service status
echo "1. Checking podman service status..."
systemctl --user status podman.socket || echo "❌ Podman socket not running"
systemctl --user status podman.service || echo "❌ Podman service not running"

# 2. Check for hung processes
echo -e "\n2. Checking for hung podman processes..."
ps aux | grep -i podman | grep -v grep

# 3. Check podman storage
echo -e "\n3. Checking podman storage..."
timeout 10 podman system info 2>/dev/null || echo "❌ podman system info timed out"

# 4. Check for locked files
echo -e "\n4. Checking for locked storage files..."
lsof +D ~/.local/share/containers 2>/dev/null | head -10 || echo "No locked files in containers storage"

# 5. Check for orphaned network namespaces
echo -e "\n5. Checking network namespaces..."
ip netns list | grep -E "cni|podman" || echo "No podman network namespaces found"

# 6. Check for orphaned mount points
echo -e "\n6. Checking for orphaned mount points..."
mount | grep -E "overlay|containers" | head -5 || echo "No suspicious mount points"

echo -e "\n🛠️  Potential fixes to try:"
echo "================================"
echo "1. Stop and restart podman services:"
echo "   systemctl --user stop podman.socket podman.service"
echo "   systemctl --user start podman.socket"
echo ""
echo "2. Kill hung podman processes:"
echo "   pkill -f podman"
echo "   pkill -f conmon"
echo ""
echo "3. Reset podman storage (WARNING: destroys all containers/images):"
echo "   podman system reset"
echo ""
echo "4. Clean up network namespaces:"
echo "   sudo ip netns list | grep -E 'cni|podman' | xargs -r sudo ip netns delete"
echo ""
echo "5. Unmount orphaned overlay mounts:"
echo "   sudo umount \$(mount | grep overlay | grep containers | cut -d' ' -f3)"
echo ""
echo "6. Clear podman cache and tmp files:"
echo "   rm -rf ~/.cache/containers/*"
echo "   rm -rf /tmp/podman-*"
echo ""
echo "7. If all else fails, use docker instead:"
echo "   export FORCE_DOCKER=1"
echo "   code-indexer start --force-docker"