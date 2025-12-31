# Installation Guide

Complete installation guide for Code Indexer (CIDX) across all platforms and scenarios.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
  - [pipx (Recommended)](#pipx-recommended)
  - [pip with Virtual Environment](#pip-with-virtual-environment)
  - [Development Installation](#development-installation)
- [Environment Setup](#environment-setup)
- [Global Registry Setup](#global-registry-setup)
- [Verification](#verification)
- [Platform-Specific Notes](#platform-specific-notes)
- [Upgrading](#upgrading)
- [Troubleshooting](#troubleshooting)
- [Uninstallation](#uninstallation)

## Prerequisites

### System Requirements

- **Python**: Version 3.9 or higher
- **RAM**: 4GB minimum (8GB+ recommended for large codebases)
- **Disk Space**: 500MB for installation + index storage (varies by codebase size)
- **Network**: Internet connection for VoyageAI API (semantic search)

### Verify Python Version

```bash
python3 --version
# Should output: Python 3.9.x or higher
```

If Python 3.9+ is not installed:
- **Ubuntu/Debian**: `sudo apt install python3.11`
- **macOS**: `brew install python@3.11`
- **Windows**: Download from [python.org](https://www.python.org/downloads/)

### Install pipx (Recommended)

pipx isolates CIDX in its own environment and makes it globally available:

```bash
# Ubuntu/Debian
sudo apt install pipx
pipx ensurepath

# macOS
brew install pipx
pipx ensurepath

# Any platform with pip
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

**After installation, restart your shell** to ensure PATH is updated.

## Installation Methods

### pipx (Recommended)

Best for most users - provides isolated environment with global command access:

```bash
# Install the package
pipx install git+https://github.com/jsbattig/code-indexer.git@v8.4.46

# Verify installation
cidx --version
```

[Corrected by fact-checker: Removed `cidx setup-global-registry` command - this is DEPRECATED as of v8.0 container cleanup. The command still exists but displays deprecation notice stating "deprecated - no longer needed" since filesystem backend doesn't require port coordination or registry setup. See cli.py:setup_global_registry function.]

**If `cidx` command is not found** after installation:

```bash
# Add pipx bin directory to PATH
export PATH="$HOME/.local/bin:$PATH"

# Make permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### pip with Virtual Environment

For users who prefer traditional virtual environments:

```bash
# Create virtual environment
python3 -m venv code-indexer-env

# Activate environment
source code-indexer-env/bin/activate  # Linux/macOS
# OR
code-indexer-env\Scripts\activate     # Windows

# Install CIDX
pip install git+https://github.com/jsbattig/code-indexer.git@v8.4.46

# Verify installation
cidx --version
```

**Note**: You must activate the virtual environment each time before using CIDX:
```bash
source code-indexer-env/bin/activate
```

### Development Installation

For contributors or those who want to modify CIDX:

```bash
# Clone repository
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
cidx --version

# Run tests to ensure everything works
./ci-github.sh
```

**Development dependencies include**:
- pytest (testing framework)
- ruff (linter)
- black (code formatter)
- mypy (type checker)

## Environment Setup

CIDX requires VoyageAI API key for semantic search functionality.

### 1. Get VoyageAI API Key

1. Sign up at [https://www.voyageai.com/](https://www.voyageai.com/)
2. Navigate to API Keys section
3. Generate a new API key
4. Copy the key (starts with `pa-...`)

### 2. Configure API Key

**Option A: Environment Variable (Recommended)**

```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
export VOYAGE_API_KEY="your-api-key-here"

# Reload shell configuration
source ~/.bashrc  # or ~/.zshrc
```

**Option B: .env File (Per-Project)**

```bash
# In your project directory
echo 'VOYAGE_API_KEY=your-api-key-here' > .env.local
```

[Corrected by fact-checker: Changed .env.local format from `export VOYAGE_API_KEY="..."` to `VOYAGE_API_KEY=...` (no export statement). Note: CIDX does NOT automatically load .env.local files. The .env.local file is referenced in mcpb/bridge.py for the MCP bridge component only, not for CLI operations. For CLI usage, set VOYAGE_API_KEY via shell environment variable as shown in Option A.]

**Option C: System-Wide Configuration**

```bash
# Add to your shell profile for persistent environment variable
echo 'export VOYAGE_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

[Corrected by fact-checker: Removed ~/.config/cidx/config.env reference - this directory/file does NOT exist in CIDX implementation. There is no code in src/code_indexer/ that reads from ~/.config/cidx/. The correct system-wide approach is to add VOYAGE_API_KEY to shell profile (.bashrc, .zshrc, etc.) as shown in Option A and this corrected Option C.]

### 3. Verify API Key Setup

```bash
# Check if environment variable is set
echo $VOYAGE_API_KEY

# Should output your API key
```

## Global Registry Setup (DEPRECATED - No Longer Required)

[Corrected by fact-checker: This entire section describes a DEPRECATED feature. The `cidx setup-global-registry` command is marked as "deprecated - no longer needed" in cli.py since v8.0 container cleanup (Story #506). The filesystem backend doesn't require port coordination or global registry setup.]

**Important**: You can skip this section entirely. CIDX v8.0+ uses filesystem-based storage that doesn't require a global registry.

The `~/.code-indexer/` directory is still used by CIDX server mode for storing golden repositories and user data, but does NOT require manual setup via `cidx setup-global-registry` command. The directory is created automatically when needed.

## Verification

### Basic Verification

```bash
# 1. Check version
cidx --version
# Output: code-indexer, version 8.4.46

# 2. Check help
cidx --help
# Should display command list

# 3. Verify API key
echo $VOYAGE_API_KEY
# Should display your key
```

### Full Verification (Test Indexing)

```bash
# Navigate to a small test project
cd /path/to/test/project

# Initialize CIDX
cidx init

# Index the project
cidx index

# Test semantic search
cidx query "your search term" --limit 5

# Cleanup
cidx clean-data
```

If all steps complete without errors, installation is successful!

## Platform-Specific Notes

### Linux (Ubuntu/Debian)

**Additional dependencies for SCIP indexing**:
```bash
# Java projects
sudo apt install openjdk-17-jdk

# Node.js projects
sudo apt install nodejs npm

# Python projects (already have Python)
```

**PATH issues**: If `cidx` not found after pipx install:
```bash
pipx ensurepath
# Restart shell
```

### macOS

**Homebrew recommended** for dependencies:
```bash
# Java projects
brew install openjdk@17

# Node.js projects
brew install node

# Python projects (already have Python via Homebrew)
```

**Apple Silicon (M1/M2/M3) Notes**:
- Use ARM-native Python (`brew install python`)
- VoyageAI API works natively, no Rosetta needed

### Windows

**Use PowerShell or Windows Terminal** (not CMD):

```powershell
# Install Python from python.org
# Ensure "Add Python to PATH" is checked during installation

# Install pipx
python -m pip install --user pipx
python -m pipx ensurepath

# Restart terminal

# Install CIDX
pipx install git+https://github.com/jsbattig/code-indexer.git@v8.4.46
```

**Path issues**: If `cidx` not found:
```powershell
# Add to PATH manually
$env:Path += ";$env:USERPROFILE\.local\bin"

# Make permanent via System Environment Variables
```

**SCIP indexing**: Install required SDKs:
- **Java**: [OpenJDK 17](https://adoptium.net/)
- **Node.js**: [Node.js LTS](https://nodejs.org/)
- **.NET**: [.NET SDK](https://dotnet.microsoft.com/download)

## Upgrading

### Upgrade to Latest Version

**pipx installation**:
```bash
pipx upgrade code-indexer
```

**pip installation**:
```bash
# Activate virtual environment first
source code-indexer-env/bin/activate

# Upgrade
pip install --upgrade git+https://github.com/jsbattig/code-indexer.git@master
```

### Upgrade to Specific Version

```bash
# pipx
pipx install --force git+https://github.com/jsbattig/code-indexer.git@v8.4.46

# pip
pip install --force-reinstall git+https://github.com/jsbattig/code-indexer.git@v8.4.46
```

### Post-Upgrade Steps

After upgrading, you may need to reindex projects:

```bash
# Navigate to project
cd /path/to/project

# Clear old indexes
cidx clean-data

# Reindex with new version
cidx index
```

**Migration guides**: See [Migration Guide](migration-to-v8.md) for major version upgrades.

## Troubleshooting

### Command Not Found: cidx

**Symptoms**: `bash: cidx: command not found`

**Solutions**:

1. **Ensure pipx bin directory in PATH**:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

2. **Verify installation**:
   ```bash
   pipx list | grep code-indexer
   ```

3. **Reinstall**:
   ```bash
   pipx uninstall code-indexer
   pipx install git+https://github.com/jsbattig/code-indexer.git@v8.4.46
   ```

### Python Version Too Old

**Symptoms**: `ERROR: This package requires Python >=3.9`

**Solutions**:

1. **Check Python version**:
   ```bash
   python3 --version
   ```

2. **Install Python 3.9+**:
   ```bash
   # Ubuntu/Debian
   sudo apt install python3.11

   # macOS
   brew install python@3.11
   ```

3. **Use specific Python version**:
   ```bash
   python3.11 -m pipx install git+https://github.com/jsbattig/code-indexer.git@v8.4.46
   ```

### VoyageAI API Key Not Found

**Symptoms**: `ERROR: VOYAGE_API_KEY environment variable not set`

**Solutions**:

1. **Set environment variable**:
   ```bash
   export VOYAGE_API_KEY="your-key-here"
   ```

2. **Add to shell profile**:
   ```bash
   echo 'export VOYAGE_API_KEY="your-key-here"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. **Use .env file** (MCP bridge only):
   ```bash
   echo 'VOYAGE_API_KEY=your-key-here' > .env.local
   ```
   Note: .env.local only works with CIDX MCP bridge, not with CLI commands.

### Permission Denied Errors

**Symptoms**: `Permission denied: '.code-indexer'`

**Solutions**:

1. **Check directory permissions**:
   ```bash
   ls -la .code-indexer
   ```

2. **Fix ownership**:
   ```bash
   sudo chown -R $USER:$USER .code-indexer
   ```

3. **Fix permissions**:
   ```bash
   chmod -R 755 .code-indexer
   ```

### Installation Fails: Build Dependencies Missing

**Symptoms**: `ERROR: Failed building wheel for [package]`

**Solutions**:

1. **Ubuntu/Debian - Install build tools**:
   ```bash
   sudo apt install build-essential python3-dev
   ```

2. **macOS - Install Xcode Command Line Tools**:
   ```bash
   xcode-select --install
   ```

3. **Windows - Install Visual C++ Build Tools**:
   - Download from [Microsoft](https://visualstudio.microsoft.com/downloads/)
   - Select "Desktop development with C++"

### Global Registry Not Created (DEPRECATED Issue)

[Corrected by fact-checker: This troubleshooting section is obsolete. The `cidx setup-global-registry` command is deprecated since v8.0. CIDX no longer requires registry.json for normal CLI operations. The ~/.code-indexer/ directory is used by CIDX server mode and created automatically when needed.]

**Note**: If you see registry-related errors, you're likely using an outdated workflow or documentation. CIDX v8.0+ uses filesystem-based storage without requiring registry setup.

### SCIP Indexing Fails

**Symptoms**: `ERROR: No SCIP indexer found for language`

**Solutions**:

1. **Install language-specific dependencies**:
   ```bash
   # Java/Kotlin
   sudo apt install openjdk-17-jdk  # Linux
   brew install openjdk@17          # macOS

   # TypeScript/JavaScript
   sudo apt install nodejs npm      # Linux
   brew install node                # macOS

   # C#
   # Install .NET SDK from microsoft.com

   # Go
   sudo apt install golang-go       # Linux
   brew install go                  # macOS
   ```

2. **Verify indexer availability**:
   ```bash
   cidx scip status
   ```

## Uninstallation

### Remove CIDX

**pipx installation**:
```bash
pipx uninstall code-indexer
```

**pip installation**:
```bash
# Activate virtual environment
source code-indexer-env/bin/activate

# Uninstall
pip uninstall code-indexer

# Remove virtual environment
deactivate
rm -rf code-indexer-env
```

### Clean Up Data

```bash
# Remove global registry
rm -rf ~/.code-indexer

# Remove per-project indexes
cd /path/to/project
cidx clean-data  # Run before uninstalling
# OR manually
rm -rf .code-indexer
```

### Complete Cleanup

```bash
# 1. Uninstall CIDX
pipx uninstall code-indexer

# 2. Remove global registry
rm -rf ~/.code-indexer

# 3. Remove environment variables (edit shell profile)
# Remove: export VOYAGE_API_KEY="..."

# 4. Remove .env files from projects
find . -name ".env.local" -type f -delete
```

---

## Next Steps

After successful installation:

1. **Index your first project**: [Quick Start Guide](../README.md#quick-start)
2. **Learn query syntax**: [Query Guide](query-guide.md)
3. **Explore SCIP**: [SCIP Code Intelligence](scip/README.md)
4. **Set up watch mode**: [Operating Modes](operating-modes.md)

---

## Getting Help

- **Documentation**: [Main README](../README.md)
- **Issues**: [GitHub Issues](https://github.com/jsbattig/code-indexer/issues)
- **Architecture**: [Architecture Guide](architecture.md)
- **Migration**: [Migration Guide](migration-to-v8.md)

---

