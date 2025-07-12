#!/bin/bash
# Fast availability check for cidx - suitable for agent solutions
# Returns quickly without waiting for timeouts

# Check if containers exist and are running
check_containers_running() {
    local container_cmd="podman"
    
    # Check if we should use docker instead
    if ! command -v podman &> /dev/null || [ "$1" = "--force-docker" ]; then
        if command -v docker &> /dev/null; then
            container_cmd="docker"
        else
            echo "❌ No container runtime found"
            return 1
        fi
    fi
    
    # Check for any cidx containers
    local containers=$($container_cmd ps --format "{{.Names}}" 2>/dev/null | grep -E "cidx-.*-(qdrant|ollama|data-cleaner)" | wc -l)
    
    if [ "$containers" -gt 0 ]; then
        echo "✅ Containers running"
        return 0
    else
        echo "❌ No cidx containers running"
        return 1
    fi
}

# Fast config check
check_config_exists() {
    # Walk up directory tree looking for .code-indexer/config.json
    local dir="$PWD"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/.code-indexer/config.json" ]; then
            echo "✅ Config found at $dir"
            return 0
        fi
        dir=$(dirname "$dir")
    done
    
    # Check home directory
    if [ -f "$HOME/.code-indexer/config.json" ]; then
        echo "✅ Config found at $HOME"
        return 0
    fi
    
    echo "❌ No config found"
    return 1
}

# Main check
echo "🔍 Quick cidx availability check..."
echo ""

# Check config
config_ok=false
if check_config_exists; then
    config_ok=true
fi

# Check containers
containers_ok=false
if check_containers_running "$@"; then
    containers_ok=true
fi

echo ""

# Summary
if [ "$config_ok" = true ] && [ "$containers_ok" = true ]; then
    echo "✅ cidx is available and ready"
    exit 0
elif [ "$config_ok" = true ] && [ "$containers_ok" = false ]; then
    echo "⚠️  cidx is configured but services are not running"
    echo "   Run 'cidx start' to start services"
    exit 1
else
    echo "❌ cidx is not configured in this directory"
    echo "   Run 'cidx init' to set up"
    exit 2
fi