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

# Simple HTTP server using netcat - fixed version
while true; do
    # Listen for ONE HTTP request and respond (no background process)
    echo -e "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nCleanup service ready\r\n" | nc -l -p 8091
    
    # The nc command blocks until a request comes in, handles it, then exits
    # The while loop then starts a new nc process for the next request
    echo "Handled one request, waiting for next..."
done