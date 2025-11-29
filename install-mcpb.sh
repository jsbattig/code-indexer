#!/bin/bash
set -e

echo "🔧 CIDX MCPB Installation Script"
echo "=================================="
echo ""

# Check if running as correct user
if [ "$USER" != "seba.battig" ]; then
    echo "❌ Error: Must run as seba.battig user"
    echo "Switch with: sudo su seba.battig"
    exit 1
fi

# Set installation directory
INSTALL_DIR="$HOME/Dev/code-indexer"
echo "📁 Installation directory: $INSTALL_DIR"

# Clone or update repository
if [ -d "$INSTALL_DIR" ]; then
    echo "📦 Updating existing repository..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "📦 Cloning repository..."
    mkdir -p "$HOME/Dev"
    cd "$HOME/Dev"
    git clone https://github.com/jsbattig/code-indexer.git
    cd code-indexer
fi

# Install dependencies
echo "📚 Installing dependencies..."
pip3 install --break-system-packages -e .

# Verify mcpb command
echo "✅ Verifying installation..."
if python3 -m code_indexer.mcpb --help > /dev/null 2>&1; then
    echo "✅ MCPB installed successfully!"
    echo ""
    echo "🔐 Next steps:"
    echo "1. Set up encrypted credentials:"
    echo "   python3 -m code_indexer.mcpb --setup-credentials"
    echo ""
    echo "2. Update Claude Desktop config to use mcpb"
    echo ""
    echo "📖 For more info, see: https://github.com/jsbattig/code-indexer"
else
    echo "❌ Installation verification failed"
    exit 1
fi
