#!/bin/bash

# Setup script for Code Indexer Global Port Registry
# This script prepares the system for multi-user cidx installations

set -e

# Check for help flag
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    cat << 'EOF'
Code Indexer Global Port Registry Setup Script
==============================================

OVERVIEW:
This script sets up a system-wide port coordination registry that prevents port 
conflicts when multiple code-indexer projects run simultaneously across different 
users and directories.

WHAT THIS SCRIPT DOES:

🔧 CREATES GLOBAL REGISTRY INFRASTRUCTURE
   • Creates /var/lib/code-indexer/port-registry/ (SINGLE SYSTEM LOCATION)
   • Sets up subdirectories for project coordination and soft links
   • NO FALLBACKS - ensures single point of coordination

🔐 CONFIGURES MULTI-USER PERMISSIONS  
   • Sets directory permissions to 777 (world-writable, no sticky bit)
   • Creates files with 666 permissions for cross-user access
   • Ensures atomic file operations work across different user contexts
   • Tests write access for regular users after setup

📁 INITIALIZES REGISTRY FILES
   • port-allocations.json - Central registry of allocated ports per project
   • registry.log - Operational log for debugging coordination issues
   • active-projects/ - Directory for soft link coordination between projects

🚀 ENABLES PORT COORDINATION FEATURES
   • Dynamic port allocation within defined ranges:
     - Qdrant: 6333-7333 (1000 ports available)
     - Ollama: 11434-12434 (1000 ports available) 
     - Data Cleaner: 8091-9091 (1000 ports available)
   • Soft link-based project coordination prevents conflicts
   • Automatic cleanup of broken links frees unused ports
   • Cross-filesystem support at single system location

WHY WE DO EACH OPERATION:

1. SYSTEM-WIDE LOCATION (/var/lib/):
   Why: Provides persistent storage that survives reboots and user session changes
   Purpose: Enables coordination between projects across different users and terminals

2. WORLD-WRITABLE PERMISSIONS (777/666):
   Why: Different users need to coordinate port allocation
   Purpose: Allows any user to participate in global port coordination
   Security: Limited to port coordination data only, no executable code

3. NO STICKY BIT ON DIRECTORIES:
   Why: Sticky bit can interfere with atomic file operations across users
   Purpose: Ensures atomic file operations work reliably for port coordination
   Technical: Allows proper cleanup of temporary files during atomic operations

4. SOFT LINK COORDINATION:
   Why: Provides lock-free coordination mechanism between projects
   Purpose: Projects can discover each other and coordinate port usage
   Benefit: No blocking operations, automatic cleanup when projects end

5. SINGLE LOCATION REQUIREMENT:
   Why: Multiple registry locations cause port conflicts and fragmentation
   Purpose: Ensures all projects coordinate through single point of truth
   Benefit: No registry fragmentation, predictable coordination behavior

6. ACCESS TESTING:
   Why: Permissions setup can fail silently in some environments
   Purpose: Validates that regular users can actually use the registry
   Reliability: Prevents runtime failures during cidx operations

WHEN TO RUN THIS SCRIPT:

✅ Required if: cidx init shows "Global port registry not accessible"
✅ Recommended: Before first use in multi-user environments
✅ Optional: After system updates that might change /var/lib permissions
✅ Never needed: For single-user systems (but harmless to run)

USAGE:
  sudo ./setup-global-registry.sh    # REQUIRED - system-wide setup (NO ALTERNATIVES)

TROUBLESHOOTING:
• If script fails with sudo: Check if /var/lib exists and is writable
• If registry not accessible after setup: Verify no AppArmor/SELinux restrictions
• If ports still conflict: Check that cidx version >= 2.14.0 (has registry support)

WHAT HAPPENS AFTER SETUP:
• All cidx commands automatically coordinate port allocation
• Projects get unique ports without configuration
• Port conflicts between projects are eliminated
• Registry automatically cleans up unused ports
• No further user action required

This is a one-time setup that enables robust multi-project coordination.
EOF
    exit 0
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration - SINGLE LOCATION ONLY, NO FALLBACKS
REGISTRY_DIR="/var/lib/code-indexer/port-registry"

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Try to set up registry in preferred location
setup_registry() {
    local registry_dir="$1"
    local description="$2"
    local use_sudo="$3"
    
    print_status "Setting up $description: $registry_dir"
    
    # Use sudo if requested
    local SUDO_CMD=""
    if [[ "$use_sudo" == "true" ]]; then
        SUDO_CMD="sudo"
        print_status "Using sudo for system-wide setup"
    fi
    
    # Create the directory first
    if ! $SUDO_CMD mkdir -p "$registry_dir" 2>/dev/null; then
        print_error "Cannot create directory $registry_dir"
        return 1
    fi
    
    # Set permissions for multi-user access (world-writable without sticky bit)
    # The sticky bit can interfere with atomic file operations across users
    if [[ -n "$SUDO_CMD" ]]; then
        $SUDO_CMD chmod 777 "$registry_dir"  # World writable (no sticky bit for atomic operations)
    fi
    
    # Test write access (without sudo to verify regular users can access)
    if ! touch "$registry_dir/test-access" 2>/dev/null; then
        print_error "Cannot write to $registry_dir (even after setup)"
        return 1
    fi
    rm -f "$registry_dir/test-access"
    
    # Create subdirectories
    $SUDO_CMD mkdir -p "$registry_dir/active-projects" || return 1
    
    # Set permissions on subdirectories (no sticky bit for atomic operations)
    if [[ -n "$SUDO_CMD" ]]; then
        $SUDO_CMD chmod 777 "$registry_dir/active-projects"
    fi
    
    # Create initial files with proper ownership
    if [[ -n "$SUDO_CMD" ]]; then
        # Create files as root but with world-writable permissions
        $SUDO_CMD touch "$registry_dir/port-allocations.json" || return 1
        $SUDO_CMD touch "$registry_dir/registry.log" || return 1
        
        # Set permissions and ownership for multi-user access
        $SUDO_CMD chmod 666 "$registry_dir/port-allocations.json"
        $SUDO_CMD chmod 666 "$registry_dir/registry.log"
        
        # Initialize with empty JSON object
        echo '{}' | $SUDO_CMD tee "$registry_dir/port-allocations.json" > /dev/null
    else
        # Non-sudo setup
        touch "$registry_dir/port-allocations.json" || return 1
        touch "$registry_dir/registry.log" || return 1
        echo '{}' > "$registry_dir/port-allocations.json"
    fi
    
    print_status "$description setup complete: $registry_dir"
    return 0
}

# Setup strategy: SINGLE LOCATION ONLY - NO FALLBACKS
print_status "Setting up Code Indexer Global Port Registry"
print_status "Location: $REGISTRY_DIR"
echo

if setup_registry "$REGISTRY_DIR" "global port registry" "true"; then
    print_status "✅ Global port registry setup successful"
else
    print_error "❌ Failed to set up registry at $REGISTRY_DIR"
    print_error "This script MUST be run with sudo for proper system-wide access:"
    print_error "sudo $0"
    exit 1
fi

# Test registry access
print_status "Testing registry access..."

# Test write access
TEST_FILE="$REGISTRY_DIR/test-access-final"
if echo "test" > "$TEST_FILE" 2>/dev/null; then
    rm -f "$TEST_FILE"
    print_status "Registry access test passed ✓"
else
    print_error "Registry access test failed ✗"
    exit 1
fi

print_status "Setup completed successfully!"

# Show usage instructions
echo
echo "Usage Instructions:"
echo "=================="
echo "The global port registry is now configured for cidx."
echo "All cidx commands will automatically coordinate port allocation."
echo
echo "Registry Location: $REGISTRY_DIR"
echo
echo "Location Details:"
echo "  ✅ System location - optimal for multi-user access, persistent across reboots"
echo
echo "No further action required - cidx will handle everything automatically."