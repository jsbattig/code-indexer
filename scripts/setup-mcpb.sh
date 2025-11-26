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
INSTALL_DIR="$HOME/.local/bin"
MCPB_BINARY="$INSTALL_DIR/mcpb"
GITHUB_REPO="jsbattig/code-indexer"
MCPB_VERSION="v8.3.0"

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

    if ! command -v unzip &> /dev/null; then
        missing_deps+=("unzip")
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

# Detect platform
detect_platform() {
    local os_type=$(uname -s)
    local arch=$(uname -m)

    local platform=""
    local binary_name=""

    case "$os_type" in
        Darwin)
            case "$arch" in
                arm64|aarch64)
                    platform="darwin-arm64"
                    binary_name="mcpb-darwin-arm64.mcpb"
                    ;;
                x86_64)
                    platform="darwin-x64"
                    binary_name="mcpb-darwin-x64.mcpb"
                    ;;
                *)
                    print_error "Unsupported macOS architecture: $arch"
                    return 1
                    ;;
            esac
            ;;
        Linux)
            case "$arch" in
                x86_64)
                    platform="linux-x64"
                    binary_name="mcpb-linux-x64.mcpb"
                    ;;
                *)
                    print_error "Unsupported Linux architecture: $arch"
                    print_error "Only x86_64 is supported"
                    return 1
                    ;;
            esac
            ;;
        MINGW*|MSYS*|CYGWIN*)
            case "$arch" in
                x86_64)
                    platform="windows-x64"
                    binary_name="mcpb-windows-x64.mcpb.exe"
                    ;;
                *)
                    print_error "Unsupported Windows architecture: $arch"
                    return 1
                    ;;
            esac
            ;;
        *)
            print_error "Unsupported operating system: $os_type"
            return 1
            ;;
    esac

    export DETECTED_PLATFORM="$platform"
    export BINARY_NAME="$binary_name"

    print_info "Detected platform: $platform"
    return 0
}

# Download MCPB binary
download_mcpb_binary() {
    local binary_name="$BINARY_NAME"
    local download_url="https://github.com/${GITHUB_REPO}/releases/download/${MCPB_VERSION}/${binary_name}"
    local temp_file="/tmp/${binary_name}"

    print_info "Downloading MCPB binary from GitHub releases..."
    print_info "URL: $download_url"

    # Download binary
    if ! curl -L -f -o "$temp_file" "$download_url" 2>/dev/null; then
        print_error "Failed to download MCPB binary"
        print_error "URL: $download_url"
        print_error "Please check:"
        print_error "  1. Internet connection is working"
        print_error "  2. GitHub releases are accessible"
        print_error "  3. Version $MCPB_VERSION exists"
        return 1
    fi

    # Verify download
    if [ ! -f "$temp_file" ] || [ ! -s "$temp_file" ]; then
        print_error "Downloaded file is missing or empty"
        return 1
    fi

    export TEMP_BINARY="$temp_file"
    print_success "Binary downloaded successfully"
    return 0
}

# Install MCPB binary
install_mcpb_binary() {
    local temp_binary="$TEMP_BINARY"

    print_info "Installing MCPB binary..."

    # Create install directory if it doesn't exist
    if [ ! -d "$INSTALL_DIR" ]; then
        print_info "Creating installation directory: $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR" || {
            print_error "Failed to create directory: $INSTALL_DIR"
            print_error "Please check directory permissions"
            return 1
        }
    fi

    # Create temp extraction directory
    local temp_extract_dir=$(mktemp -d)
    print_info "Extracting binary from .mcpb bundle..."

    # Extract the ZIP bundle
    if ! unzip -q "$temp_binary" -d "$temp_extract_dir"; then
        print_error "Failed to extract .mcpb bundle"
        rm -rf "$temp_extract_dir"
        return 1
    fi

    # The binary is located at server/mcpb-<platform> inside the ZIP
    local extracted_binary="$temp_extract_dir/server/mcpb-${DETECTED_PLATFORM}"

    if [ ! -f "$extracted_binary" ]; then
        print_error "Extracted binary not found at: $extracted_binary"
        print_error "Bundle contents:"
        ls -la "$temp_extract_dir" "$temp_extract_dir/server" 2>/dev/null || true
        rm -rf "$temp_extract_dir"
        return 1
    fi

    # Copy extracted binary to install location
    if ! cp "$extracted_binary" "$MCPB_BINARY"; then
        print_error "Failed to copy binary to: $MCPB_BINARY"
        print_error "Please check write permissions for: $INSTALL_DIR"
        rm -rf "$temp_extract_dir"
        return 1
    fi

    # Make binary executable
    if ! chmod +x "$MCPB_BINARY"; then
        print_error "Failed to make binary executable: $MCPB_BINARY"
        rm -rf "$temp_extract_dir"
        return 1
    fi

    # Clean up temp files
    rm -f "$temp_binary"
    rm -rf "$temp_extract_dir"

    print_success "MCPB binary installed to: $MCPB_BINARY"

    # Verify installation
    if [ -x "$MCPB_BINARY" ]; then
        local version_output=$("$MCPB_BINARY" --version 2>&1 || echo "unknown")
        print_success "Installation verified: $version_output"
    else
        print_warning "Binary installed but verification failed"
    fi

    return 0
}

# Check if install directory is in PATH
check_path() {
    print_info "Checking PATH configuration..."

    if echo "$PATH" | grep -q "$INSTALL_DIR"; then
        print_success "$INSTALL_DIR is in your PATH"
        export PATH_CONFIGURED=true
    else
        print_warning "$INSTALL_DIR is not in your PATH"
        export PATH_CONFIGURED=false

        echo ""
        echo "To use the 'mcpb' command from anywhere, add this line to your shell configuration:"
        echo ""

        # Detect shell and provide appropriate instructions
        local shell_name=$(basename "$SHELL")
        case "$shell_name" in
            bash)
                echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
                echo "  source ~/.bashrc"
                ;;
            zsh)
                echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
                echo "  source ~/.zshrc"
                ;;
            fish)
                echo "  fish_add_path ~/.local/bin"
                ;;
            *)
                echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
                echo "  (Add this to your shell configuration file)"
                ;;
        esac

        echo ""
        echo "Or run mcpb using the full path: $MCPB_BINARY"
        echo ""
    fi

    return 0
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

# Configure Claude Desktop MCP server
configure_claude_desktop() {
    print_info "Configuring Claude Desktop MCP server..."

    # Detect platform-specific config file location
    local claude_config_dir=""
    local claude_config_file=""

    local os_type=$(uname -s)
    case "$os_type" in
        Darwin)
            claude_config_dir="$HOME/Library/Application Support/Claude"
            ;;
        Linux)
            claude_config_dir="$HOME/.config/Claude"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            # Windows - use APPDATA
            if [ -n "$APPDATA" ]; then
                claude_config_dir="$APPDATA/Claude"
            else
                # Fallback if APPDATA not set
                claude_config_dir="$HOME/AppData/Roaming/Claude"
            fi
            ;;
        *)
            print_warning "Unsupported OS for Claude Desktop auto-configuration: $os_type"
            print_info "You can manually configure Claude Desktop using:"
            print_info "  Binary path: $MCPB_BINARY"
            export CLAUDE_DESKTOP_CONFIGURED=false
            return 0
            ;;
    esac

    claude_config_file="$claude_config_dir/claude_desktop_config.json"

    # Create config directory if it doesn't exist
    if [ ! -d "$claude_config_dir" ]; then
        print_warning "Claude Desktop config directory not found: $claude_config_dir"
        print_info "This usually means Claude Desktop is not installed"
        print_info "You can manually configure Claude Desktop later using:"
        print_info "  Binary path: $MCPB_BINARY"
        export CLAUDE_DESKTOP_CONFIGURED=false
        return 0
    fi

    print_info "Found Claude Desktop config directory: $claude_config_dir"

    # Create the MCP server entry - platform-specific environment variables
    local cidx_server_entry
    if [ "$os_type" = "Darwin" ]; then
        # macOS: Use direct environment variables (CIDX_SERVER_URL and CIDX_TOKEN)
        # Read server_url and access_token from config file if not already set
        local config_server_url="${server_url:-$(jq -r '.server_url // empty' "$CONFIG_FILE" 2>/dev/null)}"
        local config_access_token="${AUTH_ACCESS_TOKEN:-$(jq -r '.bearer_token // empty' "$CONFIG_FILE" 2>/dev/null)}"

        if [ -z "$config_server_url" ] || [ -z "$config_access_token" ]; then
            print_error "Failed to retrieve server_url or access_token for macOS configuration"
            export CLAUDE_DESKTOP_CONFIGURED=false
            return 0
        fi

        cidx_server_entry=$(jq -n \
            --arg binary_path "$MCPB_BINARY" \
            --arg url "$config_server_url" \
            --arg token "$config_access_token" \
            '{cidx: {type: "stdio", command: $binary_path, env: {CIDX_SERVER_URL: $url, CIDX_TOKEN: $token}}}')
    else
        # Linux/Windows: Use HOME environment variable (existing behavior)
        cidx_server_entry=$(jq -n \
            --arg binary_path "$MCPB_BINARY" \
            --arg home_dir "$HOME" \
            '{cidx: {type: "stdio", command: $binary_path, env: {HOME: $home_dir}}}')
    fi

    # Handle existing config file
    if [ -f "$claude_config_file" ]; then
        print_info "Updating existing Claude Desktop configuration..."

        # Read existing config and merge with new MCP server
        local updated_config=$(jq \
            --argjson new_server "$cidx_server_entry" \
            '.mcpServers = (.mcpServers // {}) + $new_server' \
            "$claude_config_file" 2>&1)

        if [ $? -ne 0 ]; then
            print_error "Failed to merge configuration with jq"
            print_error "Error: $updated_config"
            print_warning "You'll need to manually add the CIDX MCP server to: $claude_config_file"
            print_info "  Binary path: $MCPB_BINARY"
            export CLAUDE_DESKTOP_CONFIGURED=false
            return 0
        fi

        # Write updated config
        echo "$updated_config" > "$claude_config_file" || {
            print_error "Failed to write updated config to: $claude_config_file"
            print_warning "You'll need to manually add the CIDX MCP server"
            print_info "  Binary path: $MCPB_BINARY"
            export CLAUDE_DESKTOP_CONFIGURED=false
            return 0
        }

        print_success "Updated existing Claude Desktop configuration"
    else
        print_info "Creating new Claude Desktop configuration..."

        # Create new config with mcpServers section
        local new_config=$(jq -n \
            --argjson servers "$cidx_server_entry" \
            '{mcpServers: $servers}')

        # Write new config
        echo "$new_config" > "$claude_config_file" || {
            print_error "Failed to create config file: $claude_config_file"
            print_warning "You'll need to manually create the configuration"
            print_info "  Binary path: $MCPB_BINARY"
            export CLAUDE_DESKTOP_CONFIGURED=false
            return 0
        }

        print_success "Created new Claude Desktop configuration"
    fi

    print_success "Claude Desktop MCP server configured at: $claude_config_file"
    print_info "MCP server 'cidx' points to: $MCPB_BINARY"
    export CLAUDE_DESKTOP_CONFIGURED=true
    export CLAUDE_DESKTOP_CONFIG_FILE="$claude_config_file"

    return 0
}

# Display next steps
show_next_steps() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  MCPB Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Installation Summary:"
    echo "  Binary:        $MCPB_BINARY"
    echo "  Configuration: $CONFIG_FILE"
    echo "  Version:       $MCPB_VERSION"
    echo ""

    if [ "$PATH_CONFIGURED" = "true" ]; then
        echo "You can now use the 'mcpb' command from anywhere!"
        echo ""
        echo "Example usage:"
        echo "  mcpb --version"
        echo "  mcpb --help"
    else
        echo "IMPORTANT: $INSTALL_DIR is not in your PATH"
        echo ""
        echo "Use the full path until you add it to PATH:"
        echo "  $MCPB_BINARY --version"
        echo "  $MCPB_BINARY --help"
    fi

    echo ""
    echo "Additional Information:"
    echo "  1. Your bearer token is stored securely in $CONFIG_FILE"
    echo "  2. MCPB uses this configuration automatically"
    echo "  3. If the token expires, run this script again to refresh"
    echo ""

    # Claude Desktop specific instructions
    if [ "$CLAUDE_DESKTOP_CONFIGURED" = "true" ]; then
        echo -e "${GREEN}Claude Desktop Configuration:${NC}"
        echo "  Config file: $CLAUDE_DESKTOP_CONFIG_FILE"
        echo "  MCP server 'cidx' configured and ready to use"
        echo ""
        echo -e "${YELLOW}IMPORTANT: Restart Claude Desktop to activate the MCP server${NC}"
        echo ""
        echo "After restarting Claude Desktop:"
        echo "  1. The CIDX MCP server will be available automatically"
        echo "  2. You can use semantic code search through Claude"
        echo "  3. Claude can query your codebase using the 'cidx' MCP server"
        echo ""
    elif [ "$CLAUDE_DESKTOP_CONFIGURED" = "false" ]; then
        echo -e "${YELLOW}Claude Desktop Manual Configuration Required:${NC}"
        echo "  Add this to your Claude Desktop config file:"
        echo "  {"
        echo "    \"mcpServers\": {"
        echo "      \"cidx\": {"
        echo "        \"type\": \"stdio\","
        echo "        \"command\": \"$MCPB_BINARY\","

        # Platform-specific env instructions
        local os_type=$(uname -s)
        if [ "$os_type" = "Darwin" ]; then
            # macOS: Show CIDX_SERVER_URL and CIDX_TOKEN
            local config_server_url=$(jq -r '.server_url // empty' "$CONFIG_FILE" 2>/dev/null)
            local config_access_token=$(jq -r '.bearer_token // empty' "$CONFIG_FILE" 2>/dev/null)
            echo "        \"env\": {"
            echo "          \"CIDX_SERVER_URL\": \"${config_server_url:-https://your-server:8383}\","
            echo "          \"CIDX_TOKEN\": \"${config_access_token:-your-access-token}\""
            echo "        }"
        else
            # Linux/Windows: Show HOME
            echo "        \"env\": {"
            echo "          \"HOME\": \"$HOME\""
            echo "        }"
        fi

        echo "      }"
        echo "    }"
        echo "  }"
        echo ""
        echo "  Then restart Claude Desktop"
        echo ""
    fi

    echo "Manual API Usage:"
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

    # Detect platform
    if ! detect_platform; then
        print_error "Platform detection failed"
        exit 1
    fi
    echo ""

    # Check if binary already exists
    if [ -f "$MCPB_BINARY" ]; then
        print_warning "MCPB binary already exists: $MCPB_BINARY"

        # Check if we're running interactively (stdin is a terminal)
        if [ -t 0 ]; then
            # Interactive mode - ask user
            read -p "Do you want to reinstall it? (y/N): " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                # Download and install binary
                if ! download_mcpb_binary; then
                    print_error "Binary download failed"
                    exit 1
                fi

                if ! install_mcpb_binary; then
                    print_error "Binary installation failed"
                    exit 1
                fi

                check_path
                echo ""
            else
                print_info "Using existing binary"
                echo ""
            fi
        else
            # Non-interactive mode (piped from curl) - auto-reinstall
            print_info "Running in non-interactive mode - automatically reinstalling..."

            # Download and install binary
            if ! download_mcpb_binary; then
                print_error "Binary download failed"
                exit 1
            fi

            if ! install_mcpb_binary; then
                print_error "Binary installation failed"
                exit 1
            fi

            check_path
            echo ""
        fi
    else
        # Download and install binary
        if ! download_mcpb_binary; then
            print_error "Binary download failed"
            exit 1
        fi

        if ! install_mcpb_binary; then
            print_error "Binary installation failed"
            exit 1
        fi

        check_path
        echo ""
    fi

    # Check if config already exists
    if [ -f "$CONFIG_FILE" ]; then
        print_warning "Configuration file already exists: $CONFIG_FILE"

        # Check if we're running interactively (stdin is a terminal)
        if [ -t 0 ]; then
            # Interactive mode - ask user
            read -p "Do you want to overwrite it? (y/N): " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                print_info "Using existing configuration"

                # Configure Claude Desktop with existing config
                configure_claude_desktop
                echo ""

                # Show next steps
                show_next_steps

                exit 0
            fi
        else
            # Non-interactive mode (piped from curl) - use existing config
            print_info "Running in non-interactive mode - using existing configuration..."

            # Configure Claude Desktop with existing config
            configure_claude_desktop
            echo ""

            # Show next steps
            show_next_steps

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

    # Configure Claude Desktop MCP server
    configure_claude_desktop
    echo ""

    # Show next steps
    show_next_steps

    exit 0
}

# Run main script
main "$@"
