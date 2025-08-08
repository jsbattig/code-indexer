#!/bin/bash
set -e

# Code-Indexer Installation Script
# Supports multiple installation methods with cleanup and verification

VERSION="1.0.0"
SCRIPT_NAME="$(basename "$0")"
REPO_URL="https://github.com/jsbattig/code-indexer.git"
PIPX_PACKAGE="git+${REPO_URL}"

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
${SCRIPT_NAME} - Code-Indexer Installation Script v${VERSION}

USAGE:
    ${SCRIPT_NAME} [OPTIONS] [MODE]

INSTALLATION MODES:
    pipx        Install using pipx (recommended for users)
                Creates isolated environment, no system pollution
    
    system      Install system-wide using pip
                Requires sudo/admin privileges
    
    user        Install to user directory using pip --user
                No admin privileges required
    
    dev         Install for development (editable install)
                Requires local source code directory

OPTIONS:
    -h, --help          Show this help message
    -v, --version       Show version information
    -f, --force         Force installation (overwrite existing)
    -q, --quiet         Suppress non-essential output
    --dry-run          Show what would be done without executing
    --check-deps       Check dependencies before installation
    --no-verify        Skip post-installation verification

EXAMPLES:
    ${SCRIPT_NAME} pipx                    # Install via pipx (recommended)
    ${SCRIPT_NAME} user                    # Install to user directory
    ${SCRIPT_NAME} system --force          # Force system-wide installation
    ${SCRIPT_NAME} dev                     # Development installation
    ${SCRIPT_NAME} --check-deps            # Check dependencies only
    ${SCRIPT_NAME} pipx --dry-run          # Show pipx installation steps

REQUIREMENTS:
    - Python 3.9+
    - pip or pipx
    - git (for development mode)
    - Docker or Podman (runtime requirement)

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

# Check Python version
check_python_version() {
    if ! command_exists python3; then
        print_error "Python 3 is not installed"
        return 1
    fi
    
    local python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local required_version="3.9"
    
    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
        print_error "Python ${required_version}+ required, found ${python_version}"
        return 1
    fi
    
    print_success "Python ${python_version} detected"
    return 0
}

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."
    
    local deps_ok=true
    
    # Check Python
    if ! check_python_version; then
        deps_ok=false
    fi
    
    # Check pip
    if ! command_exists pip3 && ! command_exists pip; then
        print_error "pip is not installed"
        deps_ok=false
    else
        print_success "pip is available"
    fi
    
    # Check git (for dev mode)
    if ! command_exists git; then
        print_warning "git is not installed (required for development mode)"
    else
        print_success "git is available"
    fi
    
    # Check container runtime
    if command_exists docker; then
        print_success "Docker is available"
    elif command_exists podman; then
        print_success "Podman is available"
    else
        print_warning "No container runtime found (Docker or Podman recommended)"
        print_warning "Install Docker or Podman for full functionality"
    fi
    
    if [ "$deps_ok" = false ]; then
        print_error "Dependency check failed"
        return 1
    fi
    
    print_success "All required dependencies satisfied"
    return 0
}

# Install via pipx
install_pipx() {
    print_info "Installing code-indexer via pipx..."
    
    if ! command_exists pipx; then
        print_error "pipx is not installed"
        print_info "Install pipx first: python3 -m pip install --user pipx"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would run: pipx install ${PIPX_PACKAGE}"
        return 0
    fi
    
    # Remove existing installation if force is enabled
    if [ "$FORCE" = true ]; then
        print_info "Removing existing pipx installation..."
        pipx uninstall code-indexer 2>/dev/null || true
    fi
    
    pipx install "${PIPX_PACKAGE}"
    print_success "Installed via pipx"
}

# Install system-wide
install_system() {
    print_info "Installing code-indexer system-wide..."
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would run: sudo pip3 install ${PIPX_PACKAGE}"
        return 0
    fi
    
    # Check for sudo
    if ! command_exists sudo; then
        print_error "sudo is required for system-wide installation"
        return 1
    fi
    
    # Force reinstall if needed
    local force_flag=""
    if [ "$FORCE" = true ]; then
        force_flag="--force-reinstall"
        print_info "Force reinstalling..."
    fi
    
    sudo pip3 install ${force_flag} "${PIPX_PACKAGE}"
    print_success "Installed system-wide"
}

# Install to user directory
install_user() {
    print_info "Installing code-indexer to user directory..."
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would run: pip3 install --user ${PIPX_PACKAGE}"
        return 0
    fi
    
    # Force reinstall if needed
    local force_flag=""
    if [ "$FORCE" = true ]; then
        force_flag="--force-reinstall"
        print_info "Force reinstalling..."
    fi
    
    pip3 install --user ${force_flag} "${PIPX_PACKAGE}"
    print_success "Installed to user directory"
    
    # Check if user bin is in PATH
    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        print_warning "~/.local/bin is not in your PATH"
        print_info "Add this line to your ~/.bashrc or ~/.zshrc:"
        print_info "export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

# Install for development
install_dev() {
    print_info "Installing code-indexer for development..."
    
    # Check if we're in the right directory
    if [ ! -f "pyproject.toml" ] || [ ! -f "src/code_indexer/__init__.py" ]; then
        print_error "Not in code-indexer source directory"
        print_info "Clone the repository first: git clone ${REPO_URL}"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo "Would run: pip3 install -e \".[dev]\""
        return 0
    fi
    
    # Force reinstall if needed
    local force_flag=""
    if [ "$FORCE" = true ]; then
        force_flag="--force-reinstall"
        print_info "Force reinstalling..."
    fi
    
    pip3 install ${force_flag} -e ".[dev]"
    print_success "Installed for development (editable mode)"
}

# Verify installation
verify_installation() {
    if [ "$NO_VERIFY" = true ]; then
        return 0
    fi
    
    print_info "Verifying installation..."
    
    # Check if commands are available
    if command_exists cidx && command_exists code-indexer; then
        print_success "Commands 'cidx' and 'code-indexer' are available"
    else
        print_error "Installation verification failed - commands not found in PATH"
        return 1
    fi
    
    # Check version
    local version=$(cidx --version 2>/dev/null | grep -o "version [0-9.]*" | cut -d' ' -f2)
    if [ -n "$version" ]; then
        print_success "Version: $version"
    else
        print_warning "Could not determine version"
    fi
    
    print_success "Installation verified successfully"
}

# Parse command line arguments
parse_args() {
    INSTALL_MODE=""
    FORCE=false
    QUIET=false
    DRY_RUN=false
    CHECK_DEPS_ONLY=false
    NO_VERIFY=false
    
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
            --check-deps)
                CHECK_DEPS_ONLY=true
                shift
                ;;
            --no-verify)
                NO_VERIFY=true
                shift
                ;;
            pipx|system|user|dev)
                INSTALL_MODE="$1"
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
        print_info "Code-Indexer Installation Script v${VERSION}"
        echo
    fi
    
    # Check dependencies
    if ! check_dependencies; then
        exit 1
    fi
    
    # Exit if only checking dependencies
    if [ "$CHECK_DEPS_ONLY" = true ]; then
        exit 0
    fi
    
    # Default to pipx if no mode specified
    if [ -z "$INSTALL_MODE" ]; then
        print_info "No installation mode specified, defaulting to pipx"
        INSTALL_MODE="pipx"
    fi
    
    # Show dry run notice
    if [ "$DRY_RUN" = true ]; then
        print_warning "DRY RUN MODE - No actual changes will be made"
        echo
    fi
    
    # Install based on mode
    case "$INSTALL_MODE" in
        pipx)
            install_pipx
            ;;
        system)
            install_system
            ;;
        user)
            install_user
            ;;
        dev)
            install_dev
            ;;
        *)
            print_error "Invalid installation mode: $INSTALL_MODE"
            exit 1
            ;;
    esac
    
    # Verify installation unless dry run
    if [ "$DRY_RUN" != true ]; then
        verify_installation
    fi
    
    # Success message
    if [ "$DRY_RUN" != true ] && [ "$QUIET" != true ]; then
        echo
        print_success "Code-indexer installation completed successfully!"
        print_info "Run 'cidx --help' or 'code-indexer --help' to get started"
        print_info "Visit https://github.com/jsbattig/code-indexer for documentation"
    fi
}

# Run main function with all arguments
main "$@"