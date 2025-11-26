#!/bin/bash

# MCPB Configuration Setup Script
# Automates the initial configuration for MCPB (MCP Bridge) client

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONFIG_DIR="$HOME/.mcpb"
CONFIG_FILE="$CONFIG_DIR/config.json"

# Print functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."

    local missing_deps=()

    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi

    if ! command -v jq &> /dev/null; then
        missing_deps+=("jq")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing required dependencies: ${missing_deps[*]}"
        echo ""
        echo "Please install them using your package manager:"
        echo "  Ubuntu/Debian: sudo apt-get install ${missing_deps[*]}"
        echo "  Fedora/RHEL:   sudo dnf install ${missing_deps[*]}"
        echo "  macOS:         brew install ${missing_deps[*]}"
        exit 1
    fi

    print_success "All dependencies installed"
}

# Prompt for input
prompt_for_input() {
    local prompt="$1"
    local var_name="$2"
    local is_password="$3"

    if [ "$is_password" = "true" ]; then
        read -sp "$prompt" value
        echo "" # New line after password input
    else
        read -p "$prompt" value
    fi

    eval "$var_name='$value'"
}

# Validate URL format
validate_url() {
    local url="$1"
    if [[ ! "$url" =~ ^https?:// ]]; then
        print_error "Invalid URL format. Must start with http:// or https://"
        return 1
    fi
    return 0
}

# Authenticate and get tokens
authenticate() {
    local server_url="$1"
    local username="$2"
    local password="$3"

    print_info "Authenticating with server..."

    local auth_endpoint="${server_url}/auth/login"
    local payload=$(jq -n \
        --arg username "$username" \
        --arg password "$password" \
        '{username: $username, password: $password}')

    # Make authentication request
    local response
    local http_code

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$auth_endpoint" 2>&1) || {
        print_error "Network error: Failed to connect to $auth_endpoint"
        print_error "Please check your network connection and server URL"
        return 1
    }

    # Extract HTTP status code (last line)
    http_code=$(echo "$response" | tail -n1)
    # Extract response body (all but last line)
    response=$(echo "$response" | sed '$d')

    # Check HTTP status code
    if [ "$http_code" != "200" ]; then
        print_error "Authentication failed (HTTP $http_code)"

        # Try to parse error message from response
        local error_msg=$(echo "$response" | jq -r '.detail // .message // "Unknown error"' 2>/dev/null)
        if [ $? -eq 0 ] && [ "$error_msg" != "Unknown error" ]; then
            print_error "Server message: $error_msg"
        fi

        case "$http_code" in
            401)
                print_error "Invalid username or password"
                ;;
            404)
                print_error "Authentication endpoint not found. Check server URL"
                ;;
            500)
                print_error "Server error. Please contact administrator"
                ;;
            000)
                print_error "Could not connect to server. Check URL and network"
                ;;
        esac

        return 1
    fi

    # Parse tokens from response
    local access_token=$(echo "$response" | jq -r '.access_token // empty' 2>/dev/null)
    local refresh_token=$(echo "$response" | jq -r '.refresh_token // empty' 2>/dev/null)

    if [ -z "$access_token" ] || [ "$access_token" = "null" ]; then
        print_error "Failed to extract access_token from response"
        print_error "Response: $response"
        return 1
    fi

    if [ -z "$refresh_token" ] || [ "$refresh_token" = "null" ]; then
        print_warning "No refresh_token in response (may not be required)"
        refresh_token=""
    fi

    print_success "Authentication successful"

    # Export tokens for use in create_config
    export AUTH_ACCESS_TOKEN="$access_token"
    export AUTH_REFRESH_TOKEN="$refresh_token"

    return 0
}

# Create configuration directory and file
create_config() {
    local server_url="$1"
    local access_token="$AUTH_ACCESS_TOKEN"
    local refresh_token="$AUTH_REFRESH_TOKEN"

    print_info "Creating configuration directory..."

    # Create directory if it doesn't exist
    if [ ! -d "$CONFIG_DIR" ]; then
        mkdir -p "$CONFIG_DIR" || {
            print_error "Failed to create directory: $CONFIG_DIR"
            return 1
        }
        print_success "Created directory: $CONFIG_DIR"
    else
        print_info "Directory already exists: $CONFIG_DIR"
    fi

    print_info "Writing configuration file..."

    # Create config JSON
    local config
    if [ -n "$refresh_token" ]; then
        config=$(jq -n \
            --arg url "$server_url" \
            --arg bearer "$access_token" \
            --arg refresh "$refresh_token" \
            '{server_url: $url, bearer_token: $bearer, refresh_token: $refresh}')
    else
        config=$(jq -n \
            --arg url "$server_url" \
            --arg bearer "$access_token" \
            '{server_url: $url, bearer_token: $bearer}')
    fi

    # Write config file
    echo "$config" > "$CONFIG_FILE" || {
        print_error "Failed to write configuration file: $CONFIG_FILE"
        return 1
    }

    # Set secure permissions (owner read/write only)
    chmod 0600 "$CONFIG_FILE" || {
        print_error "Failed to set secure permissions on: $CONFIG_FILE"
        return 1
    }

    print_success "Configuration saved to: $CONFIG_FILE"
    print_success "File permissions set to 0600 (secure)"

    return 0
}

# Display next steps
show_next_steps() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  MCPB Configuration Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Configuration file: $CONFIG_FILE"
    echo ""
    echo "Next steps:"
    echo "  1. Your bearer token is now stored securely"
    echo "  2. You can use the MCPB client to interact with the server"
    echo "  3. If the token expires, run this script again to refresh"
    echo ""
    echo "Example usage:"
    echo "  # Query the server"
    echo "  curl -H \"Authorization: Bearer \$(jq -r .bearer_token ~/.mcpb/config.json)\" \\"
    echo "       https://your-server/api/endpoint"
    echo ""
}

# Main script
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  MCPB Configuration Setup${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # Check dependencies
    check_dependencies
    echo ""

    # Check if config already exists
    if [ -f "$CONFIG_FILE" ]; then
        print_warning "Configuration file already exists: $CONFIG_FILE"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Setup cancelled"
            exit 0
        fi
    fi

    # Prompt for server details
    echo "Please enter your MCPB server details:"
    echo ""

    local server_url username password

    # Get server URL
    while true; do
        prompt_for_input "Server URL (e.g., https://linner.ddns.net:8383): " server_url false
        if validate_url "$server_url"; then
            # Remove trailing slash if present
            server_url="${server_url%/}"
            break
        fi
    done

    # Get username
    prompt_for_input "Username: " username false

    # Get password
    prompt_for_input "Password: " password true
    echo ""

    # Validate inputs
    if [ -z "$server_url" ] || [ -z "$username" ] || [ -z "$password" ]; then
        print_error "All fields are required"
        exit 1
    fi

    # Authenticate
    if ! authenticate "$server_url" "$username" "$password"; then
        print_error "Setup failed during authentication"
        exit 1
    fi

    # Create config
    if ! create_config "$server_url"; then
        print_error "Setup failed during configuration creation"
        exit 1
    fi

    # Show next steps
    show_next_steps

    exit 0
}

# Run main script
main "$@"
