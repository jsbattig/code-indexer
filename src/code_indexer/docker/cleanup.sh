#!/bin/bash

# Simple HTTP server that responds to cleanup requests
# Runs with root privileges to remove any files

echo "Starting cleanup service on port 8091..."

# Function to handle cleanup request
handle_request() {
    local path="$1"
    
    echo "Cleanup request for: $path"
    
    if [[ -z "$path" ]]; then
        echo "ERROR: No path provided"
        return 1
    fi
    
    # Safety check - only allow specific patterns
    if [[ "$path" =~ ^/data/.*$ ]] || [[ "$path" =~ .*code-indexer.*$ ]]; then
        if [[ -e "$path" ]]; then
            echo "Removing: $path"
            rm -rf "$path"
            echo "SUCCESS: Removed $path"
            return 0
        else
            echo "WARNING: Path does not exist: $path"
            return 0
        fi
    else
        echo "ERROR: Path not allowed for cleanup: $path"
        return 1
    fi
}

# Simple HTTP server using netcat
while true; do
    # Listen for HTTP requests
    echo -e "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nCleanup service ready\r\n" | nc -l -p 8091 &
    
    # In a real implementation, we'd parse the HTTP request for the path
    # For this experiment, we'll just sleep and wait for manual testing
    sleep 10
done