#!/bin/bash
#
# cleanup-with-collections.sh
# Enhanced cleanup that removes all collections before shutting down containers
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧹 Enhanced cleanup with collection removal${NC}"

# Step 1: Check if containers are running
echo -e "${BLUE}🔍 Checking for running containers...${NC}"

# Try to detect Qdrant by checking if we can connect to it
QDRANT_RUNNING=false

# Use Python to check Qdrant health through proper configuration
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/src')
from pathlib import Path

try:
    from code_indexer.config import ConfigManager
    from code_indexer.services.qdrant import QdrantClient
    
    # Try to load config
    config_manager = ConfigManager.create_with_backtrack()
    config = config_manager.load()
    
    # Try to connect to Qdrant
    qdrant_client = QdrantClient(config.qdrant)
    if qdrant_client.health_check():
        print('QDRANT_HEALTHY')
    else:
        print('QDRANT_UNHEALTHY')
except Exception as e:
    print(f'QDRANT_ERROR: {e}')
" > /tmp/qdrant_check.txt 2>&1

if grep -q "QDRANT_HEALTHY" /tmp/qdrant_check.txt; then
    QDRANT_RUNNING=true
    echo -e "${GREEN}✅ Qdrant is running and healthy${NC}"
else
    echo -e "${YELLOW}⚠️  Qdrant is not running or not healthy${NC}"
fi

# Step 2: If Qdrant is running, clean up collections first
if [ "$QDRANT_RUNNING" = true ]; then
    echo -e "${BLUE}🗑️  Removing all collections before shutdown...${NC}"
    
    # Set force flag if requested
    if [ "$1" = "--force" ]; then
        export FORCE_CLEANUP=1
    fi
    
    # Run collection cleanup
    if python3 "$SCRIPT_DIR/cleanup-all-collections.py"; then
        echo -e "${GREEN}✅ Collection cleanup completed${NC}"
    else
        echo -e "${YELLOW}⚠️  Collection cleanup had issues (continuing anyway)${NC}"
    fi
else
    echo -e "${BLUE}ℹ️  Skipping collection cleanup (Qdrant not running)${NC}"
fi

# Step 3: Run the comprehensive test suite cleanup
echo -e "${BLUE}🧹 Running comprehensive test suite cleanup...${NC}"
"$SCRIPT_DIR/cleanup-test-suite.sh"

# Step 4: Optional - force cleanup if requested
if [ "$1" = "--force" ]; then
    echo -e "${YELLOW}🔥 Force cleanup requested - removing all containers${NC}"
    
    # Get container runtime
    if command -v podman &> /dev/null; then
        RUNTIME="podman"
    else
        RUNTIME="docker"
    fi
    
    # Find and remove all code-indexer related containers
    echo -e "${BLUE}🔍 Looking for code-indexer containers...${NC}"
    CONTAINERS=$($RUNTIME ps -a --format "{{.Names}}" | grep -E "cidx-|code-indexer" || true)
    
    if [ -n "$CONTAINERS" ]; then
        echo -e "${YELLOW}🗑️  Removing containers:${NC}"
        echo "$CONTAINERS" | while read -r container; do
            echo -e "   • $container"
            $RUNTIME rm -f "$container" 2>/dev/null || true
        done
    else
        echo -e "${BLUE}ℹ️  No code-indexer containers found${NC}"
    fi
fi

# Cleanup temp file
rm -f /tmp/qdrant_check.txt

echo -e "${GREEN}✅ Enhanced cleanup completed${NC}"