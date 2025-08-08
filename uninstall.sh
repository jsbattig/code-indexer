#!/bin/bash
set -e

# Code-Indexer Uninstallation Script
# Removes all installations and cleans up the system

VERSION="1.0.0"
SCRIPT_NAME="$(basename "$0")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

show_help() {
    cat << EOF
${SCRIPT_NAME} - Code-Indexer Uninstallation Script v${VERSION}

USAGE:
    ${SCRIPT_NAME} [OPTIONS] [MODE]

UNINSTALLATION MODES:
    all         Remove all code-indexer installations (default)
                Scans and removes pipx, system, user, and dev installations
    
    pipx        Remove only pipx installation
                Removes from pipx isolated environment
    
    system      Remove only system-wide installation
                Requires sudo/admin privileges
    
    user        Remove only user installation
                Removes from user directory (~/.local)
    
    dev         Remove only development installation
                Uninstalls editable/development mode
    
    clean       Remove all installations + configuration data
                WARNING: Also removes ~/.code-indexer and /var/lib/code-indexer

OPTIONS:
    -h, --help          Show this help message
    -v, --version       Show version information
    -f, --force         Force removal without confirmation
    -q, --quiet         Suppress non-essential output
    --dry-run          Show what would be done without executing
    --keep-config      Keep configuration files (with 'clean' mode)
    --remove-containers Stop and remove all code-indexer containers

EXAMPLES:
    ${SCRIPT_NAME}                         # Remove all installations (interactive)
    ${SCRIPT_NAME} all --force             # Force remove all installations
    ${SCRIPT_NAME} pipx                    # Remove only pipx installation  
    ${SCRIPT_NAME} clean --force           # Complete cleanup (configs too)
    ${SCRIPT_NAME} --remove-containers     # Also remove containers
    ${SCRIPT_NAME} --dry-run               # Show what would be removed

WHAT GETS REMOVED:
    • pipx: ~/.local/share/pipx/venvs/code-indexer/
    • system: /usr/local/bin/cidx, /usr/local/bin/code-indexer
    • user: ~/.local/bin/cidx, ~/.local/bin/code-indexer
    • pyenv: Python environment binaries
    • clean mode: + configuration directories

For more information: https://github.com/jsbattig/code-indexer
EOF
}

show_version() {
    echo "${SCRIPT_NAME} version ${VERSION}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Confirm action with user
confirm_action() {
    local message="$1"
    
    if [ "$FORCE" = true ]; then
        return 0
    fi
    
    echo -n -e "${YELLOW}❓ ${message} [y/N]: ${NC}"
    read -r response
    
    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Find and remove pip installations
find_pip_installations() {
    local install_type="$1"
    local installations_found=false
    
    # Check different pip commands
    for pip_cmd in pip pip3; do
        if command_exists "$pip_cmd"; then
            local pip_args=""
            
            case "$install_type" in
                user)
                    pip_args="--user"
                    ;;
                system)
                    pip_args=""
                    ;;
            esac
            
            # Check if package is installed
            if $pip_cmd list $pip_args 2>/dev/null | grep -q "^code-indexer"; then
                installations_found=true
                
                if [ "$DRY_RUN" = true ]; then
                    echo "Would run: $pip_cmd uninstall $pip_args code-indexer -y"
                    continue
                fi
                
                print_info "Removing ${install_type} installation via $pip_cmd..."
                
                if [ "$install_type" = "system" ]; then
                    if command_exists sudo; then
                        sudo $pip_cmd uninstall $pip_args code-indexer -y || true
                    else
                        print_warning "sudo not available, attempting direct uninstall..."
                        $pip_cmd uninstall $pip_args code-indexer -y || true
                    fi
                else
                    $pip_cmd uninstall $pip_args code-indexer -y || true
                fi
                
                print_success "Removed ${install_type} installation"
            fi
        fi
    done
    
    return 0
}

# Remove pipx installation
remove_pipx() {
    print_info "Checking for pipx installation..."
    
    if ! command_exists pipx; then
        print_info "pipx not found, skipping pipx uninstall"
        return 0
    fi
    
    # Check if code-indexer is installed via pipx
    if pipx list 2>/dev/null | grep -q "code-indexer"; then
        if [ "$DRY_RUN" = true ]; then
            echo "Would run: pipx uninstall code-indexer"
            return 0
        fi
        
        if confirm_action "Remove pipx installation of code-indexer?"; then
            pipx uninstall code-indexer
            print_success "Removed pipx installation"
        fi
    else
        print_info "No pipx installation found"
    fi
}

# Remove system installation
remove_system() {
    print_info "Checking for system installation..."
    
    # Check common system locations
    local system_locations=(
        "/usr/local/bin/cidx"
        "/usr/local/bin/code-indexer"
        "/usr/bin/cidx"
        "/usr/bin/code-indexer"
    )
    
    local found_system=false
    
    for location in "${system_locations[@]}"; do
        if [ -f "$location" ]; then
            found_system=true
            
            if [ "$DRY_RUN" = true ]; then
                echo "Would remove: $location"
                continue
            fi
            
            print_info "Found system installation: $location"
            if confirm_action "Remove system file $location?"; then
                if command_exists sudo; then
                    sudo rm -f "$location"
                else
                    rm -f "$location" 2>/dev/null || print_warning "Could not remove $location (permission denied)"
                fi
                print_success "Removed $location"
            fi
        fi
    done
    
    # Also try pip-based system uninstall
    find_pip_installations "system"
    
    if [ "$found_system" = false ]; then
        print_info "No system installation found"
    fi
}

# Remove user installation
remove_user() {
    print_info "Checking for user installation..."
    
    # Check user bin locations
    local user_locations=(
        "$HOME/.local/bin/cidx"
        "$HOME/.local/bin/code-indexer"
    )
    
    local found_user=false
    
    for location in "${user_locations[@]}"; do
        if [ -f "$location" ] || [ -L "$location" ]; then
            found_user=true
            
            if [ "$DRY_RUN" = true ]; then
                echo "Would remove: $location"
                continue
            fi
            
            print_info "Found user installation: $location"
            if confirm_action "Remove user file $location?"; then
                rm -f "$location"
                print_success "Removed $location"
            fi
        fi
    done
    
    # Also try pip-based user uninstall
    find_pip_installations "user"
    
    if [ "$found_user" = false ]; then
        print_info "No user installation found"
    fi
}

# Remove development installation
remove_dev() {
    print_info "Checking for development installation..."
    
    # Try to find editable installs
    for pip_cmd in pip pip3; do
        if command_exists "$pip_cmd"; then
            if $pip_cmd list 2>/dev/null | grep -q "code-indexer.*/.*/Dev/code-indexer"; then
                if [ "$DRY_RUN" = true ]; then
                    echo "Would run: $pip_cmd uninstall code-indexer -y"
                    continue
                fi
                
                if confirm_action "Remove development installation?"; then
                    $pip_cmd uninstall code-indexer -y || true
                    print_success "Removed development installation"
                    return 0
                fi
            fi
        fi
    done
    
    # Check pyenv installations
    if command_exists pyenv; then
        local pyenv_versions=$(pyenv versions --bare 2>/dev/null || true)
        for version in $pyenv_versions; do
            local pyenv_bin="$HOME/.pyenv/versions/$version/bin"
            if [ -f "$pyenv_bin/cidx" ] || [ -f "$pyenv_bin/code-indexer" ]; then
                if [ "$DRY_RUN" = true ]; then
                    echo "Would remove pyenv installation from Python $version"
                    continue
                fi
                
                print_info "Found pyenv installation in Python $version"
                if confirm_action "Remove pyenv installation from Python $version?"; then
                    # Switch to that version and uninstall
                    PYENV_VERSION=$version pip uninstall code-indexer -y 2>/dev/null || true
                    print_success "Removed pyenv installation from Python $version"
                fi
            fi
        done
    fi
    
    print_info "Development installation check completed"
}

# Remove containers
remove_containers() {
    if [ "$REMOVE_CONTAINERS" != true ]; then
        return 0
    fi
    
    print_info "Checking for code-indexer containers..."
    
    # Check both docker and podman
    for container_cmd in docker podman; do
        if command_exists "$container_cmd"; then
            # Find code-indexer containers
            local containers=$($container_cmd ps -a --format "{{.Names}}" 2>/dev/null | grep -E "cidx-.*-(qdrant|ollama|data-cleaner)" || true)
            
            if [ -n "$containers" ]; then
                if [ "$DRY_RUN" = true ]; then
                    echo "Would remove $container_cmd containers: $containers"
                    continue
                fi
                
                if confirm_action "Stop and remove $container_cmd containers ($containers)?"; then
                    for container in $containers; do
                        print_info "Stopping and removing container: $container"
                        $container_cmd stop "$container" 2>/dev/null || true
                        $container_cmd rm "$container" 2>/dev/null || true
                    done
                    print_success "Removed $container_cmd containers"
                fi
            fi
        fi
    done
}

# Clean configuration data
clean_config() {
    if [ "$REMOVE_MODE" != "clean" ]; then
        return 0
    fi
    
    if [ "$KEEP_CONFIG" = true ]; then
        print_info "Keeping configuration files (--keep-config specified)"
        return 0
    fi
    
    print_warning "DESTRUCTIVE OPERATION: This will remove all configuration data"
    
    local config_locations=(
        "$HOME/.code-indexer"
        "/var/lib/code-indexer"
    )
    
    for config_dir in "${config_locations[@]}"; do
        if [ -d "$config_dir" ]; then
            if [ "$DRY_RUN" = true ]; then
                echo "Would remove configuration directory: $config_dir"
                continue
            fi
            
            if confirm_action "PERMANENTLY DELETE configuration directory $config_dir?"; then
                if [[ "$config_dir" == "/var/lib/code-indexer" ]]; then
                    if command_exists sudo; then
                        sudo rm -rf "$config_dir"
                    else
                        print_warning "Cannot remove $config_dir without sudo"
                        continue
                    fi
                else
                    rm -rf "$config_dir"
                fi
                print_success "Removed configuration directory: $config_dir"
            fi
        fi
    done
}

# Remove all installations
remove_all() {
    print_info "Scanning for all code-indexer installations..."
    
    remove_pipx
    remove_system  
    remove_user
    remove_dev
}

# Verify removal
verify_removal() {
    if [ "$DRY_RUN" = true ]; then
        return 0
    fi
    
    print_info "Verifying removal..."
    
    if command_exists cidx || command_exists code-indexer; then
        print_warning "Commands still found in PATH - some installations may remain"
        
        # Show remaining installations
        if command_exists cidx; then
            local cidx_location=$(which cidx)
            print_info "Remaining cidx: $cidx_location"
        fi
        
        if command_exists code-indexer; then
            local code_indexer_location=$(which code-indexer)
            print_info "Remaining code-indexer: $code_indexer_location"
        fi
    else
        print_success "All installations removed successfully"
    fi
}

# Parse command line arguments
parse_args() {
    REMOVE_MODE="all"
    FORCE=false
    QUIET=false
    DRY_RUN=false
    KEEP_CONFIG=false
    REMOVE_CONTAINERS=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--version)
                show_version
                exit 0
                ;;
            -f|--force)
                FORCE=true
                shift
                ;;
            -q|--quiet)
                QUIET=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --keep-config)
                KEEP_CONFIG=true
                shift
                ;;
            --remove-containers)
                REMOVE_CONTAINERS=true
                shift
                ;;
            all|pipx|system|user|dev|clean)
                REMOVE_MODE="$1"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                print_info "Use --help for usage information"
                exit 1
                ;;
        esac
    done
}

# Main function
main() {
    parse_args "$@"
    
    # Show banner unless quiet
    if [ "$QUIET" != true ]; then
        echo
        print_info "Code-Indexer Uninstallation Script v${VERSION}"
        echo
    fi
    
    # Show dry run notice
    if [ "$DRY_RUN" = true ]; then
        print_warning "DRY RUN MODE - No actual changes will be made"
        echo
    fi
    
    # Warning for clean mode
    if [ "$REMOVE_MODE" = "clean" ] && [ "$DRY_RUN" != true ]; then
        echo
        print_warning "CLEAN MODE SELECTED - This will remove configurations and data!"
        print_warning "This action cannot be undone."
        echo
        
        if ! confirm_action "Are you sure you want to proceed with clean mode?"; then
            print_info "Uninstallation cancelled"
            exit 0
        fi
    fi
    
    # Remove based on mode
    case "$REMOVE_MODE" in
        all)
            remove_all
            ;;
        pipx)
            remove_pipx
            ;;
        system)
            remove_system
            ;;
        user)
            remove_user
            ;;
        dev)
            remove_dev
            ;;
        clean)
            remove_all
            clean_config
            ;;
        *)
            print_error "Invalid removal mode: $REMOVE_MODE"
            exit 1
            ;;
    esac
    
    # Remove containers if requested
    remove_containers
    
    # Verify removal
    verify_removal
    
    # Success message
    if [ "$DRY_RUN" != true ] && [ "$QUIET" != true ]; then
        echo
        print_success "Code-indexer uninstallation completed!"
        
        if [ "$REMOVE_MODE" != "clean" ]; then
            print_info "Configuration files preserved"
            print_info "Use '$SCRIPT_NAME clean' to remove all data"
        fi
    fi
}

# Run main function with all arguments
main "$@"