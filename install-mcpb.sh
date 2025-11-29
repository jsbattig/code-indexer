#!/bin/bash
set -e

echo "CIDX MCPB Installation Script"
echo "=================================="
echo ""

# Check if running as correct user
if [ "$USER" != "seba.battig" ]; then
    echo "Error: Must run as seba.battig user"
    echo "Switch with: sudo su seba.battig"
    exit 1
fi

# Set installation directory
INSTALL_DIR="$HOME/Dev/code-indexer"
echo "Installation directory: $INSTALL_DIR"

# Clone or update repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing repository..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Cloning repository..."
    mkdir -p "$HOME/Dev"
    cd "$HOME/Dev"
    git clone https://github.com/jsbattig/code-indexer.git
    cd code-indexer
fi

# Install dependencies (Mac doesn't need --break-system-packages)
echo "Installing dependencies..."
pip3 install -e .

# Verify mcpb command
echo "Verifying installation..."
if ! python3 -m code_indexer.mcpb --help > /dev/null 2>&1; then
    echo "Installation verification failed"
    exit 1
fi

# Create ~/.mcpb directory
echo "Creating ~/.mcpb directory..."
mkdir -p "$HOME/.mcpb"

# Create wrapper script
echo "Creating wrapper script at ~/.mcpb/mcpb-wrapper.sh..."
cat > "$HOME/.mcpb/mcpb-wrapper.sh" << 'EOF'
#!/bin/bash
# MCPB Wrapper Script - Sets required environment for Claude Desktop
export HOME=/Users/seba.battig
export PYTHONPATH=/Users/seba.battig/Dev/code-indexer/src:/Users/seba.battig/Library/Python/3.9/lib/python/site-packages

# Execute mcpb with all arguments
exec python3 -m code_indexer.mcpb "$@"
EOF

# Make wrapper executable
chmod +x "$HOME/.mcpb/mcpb-wrapper.sh"
echo "Wrapper script created and made executable"

# Update Claude Desktop config
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

echo "Updating Claude Desktop config..."
mkdir -p "$CLAUDE_CONFIG_DIR"

# Create or update config with wrapper script
cat > "$CLAUDE_CONFIG_FILE" << EOF
{
  "mcpServers": {
    "code-indexer": {
      "command": "$HOME/.mcpb/mcpb-wrapper.sh"
    }
  }
}
EOF

echo "Claude Desktop config updated"

# Set up encrypted credentials using Python
echo "Setting up encrypted credentials (admin/admin)..."
python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/Users/seba.battig/Dev/code-indexer/src')

from code_indexer.mcpb.credential_storage import save_credentials

try:
    save_credentials('admin', 'admin')
    print("Encrypted credentials saved successfully")
except Exception as e:
    print(f"Error saving credentials: {e}")
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -ne 0 ]; then
    echo "Failed to set up encrypted credentials"
    exit 1
fi

# Restart Claude Desktop
echo "Restarting Claude Desktop..."
killall Claude 2>/dev/null || true
sleep 2
open -a Claude

echo ""
echo "Installation complete!"
echo ""
echo "Configuration summary:"
echo "  - Wrapper script: $HOME/.mcpb/mcpb-wrapper.sh"
echo "  - Claude config: $CLAUDE_CONFIG_FILE"
echo "  - Credentials: ~/.mcpb/credentials.enc (encrypted)"
echo ""
echo "Claude Desktop has been restarted and should now have MCPB server available."
echo "Check Claude Desktop's server panel to verify the code-indexer MCP server is connected."
