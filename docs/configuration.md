FACT-CHECKED

Last Fact-Check: 2025-12-31
Verified Against: CIDX source code (src/code_indexer/)

# Configuration Guide

Complete reference for configuring CIDX.

## Table of Contents

- [Overview](#overview)
- [Embedding Provider](#embedding-provider)
- [Configuration File](#configuration-file)
- [Environment Variables](#environment-variables)
- [Per-Project vs Global](#per-project-vs-global)
- [Advanced Configuration](#advanced-configuration)
- [Troubleshooting](#troubleshooting)

## Overview

CIDX configuration involves three main areas:

1. **Embedding Provider** - VoyageAI API key (required for semantic search)
2. **Configuration File** - `.code-indexer/config.json` per project
3. **Environment Variables** - Optional tuning and server settings

## Embedding Provider

### VoyageAI (Required)

CIDX uses **VoyageAI embeddings** for semantic search. This is the **only supported provider** in v8.0+.

**Get API Key**:
1. Sign up at https://www.voyageai.com/
2. Navigate to API Keys section
3. Generate new API key
4. Copy your API key

### Configure API Key

**Option 1: Environment Variable (Recommended)**

```bash
# Add to shell profile (~/.bashrc, ~/.zshrc, etc.)
export VOYAGE_API_KEY="your-api-key-here"

# Reload shell
source ~/.bashrc  # or ~/.zshrc
```

**Option 2: .env.local File (Manual Loading)**

```bash
# Create .env.local in project directory
echo 'VOYAGE_API_KEY=your-api-key-here' > .env.local

# Load into shell environment (one-time per session)
export $(cat .env.local | xargs)
```

**Important**: CIDX does NOT automatically load `.env.local` files. You must export environment variables to your shell before running `cidx` commands. The `.env.local` file is simply a convenient place to store the key - you need to load it manually using `export` or similar shell commands.

**Option 3: Per-Session**

```bash
# Set for current session only
export VOYAGE_API_KEY="your-api-key-here"

# Run CIDX commands
cidx query "search term"
```

### Verify Setup

```bash
# Check environment variable
echo $VOYAGE_API_KEY

# Should output your API key
```

### Supported Models

CIDX automatically uses VoyageAI models:

| Model | Dimensions | Use Case |
|-------|------------|----------|
| **voyage-code-3** | 1024 | Default, optimized for code |
| **voyage-large-2** | 1536 | Highest quality |

**Model Selection**: Configured in code, not user-selectable in v8.0+. Default is `voyage-code-3`.

## Configuration File

### Location

**Per-Project**: `.code-indexer/config.json` in each indexed project

Created automatically by `cidx init` or first `cidx index`.

### Structure

```json
{
  "file_extensions": [
    "py", "js", "ts", "tsx", "java", "cpp", "c", "cs", "h", "hpp",
    "go", "rs", "rb", "php", "pl", "pm", "pod", "t", "psgi",
    "sh", "bash", "html", "css", "md", "json", "yaml", "yml", "toml",
    "sql", "swift", "kt", "kts", "scala", "dart", "vue", "jsx",
    "pas", "pp", "dpr", "dpk", "inc", "lua", "xml", "xsd", "xsl",
    "xslt", "groovy", "gradle", "gvy", "gy", "cxx", "cc", "hxx",
    "rake", "rbw", "gemspec", "htm", "scss", "sass"
  ],
  "exclude_dirs": [
    "node_modules", "venv", "__pycache__", ".git", "dist", "build",
    "target", ".idea", ".vscode", ".gradle", "bin", "obj",
    "coverage", ".next", ".nuxt", "dist-*", ".code-indexer"
  ],
  "embedding_provider": "voyage-ai",
  "indexing": {
    "max_file_size": 1048576
  }
}
```

### Configuration Fields

#### file_extensions

**Type**: Array of strings (WITHOUT dot prefix)
**Default**: Common code file extensions (see structure above)
**Purpose**: File types to index

**Important**: Extensions are specified WITHOUT dots (e.g., "py" not ".py"). The system adds dots automatically.

**Customization**:
```json
{
  "file_extensions": [
    "py", "js", "ts"  // Only Python and JavaScript/TypeScript
  ]
}
```

**Add More Extensions**:
```json
{
  "file_extensions": [
    "py", "js", "ts",
    "jsx", "tsx",    // React
    "vue",            // Vue
    "svelte",         // Svelte
    "scala",          // Scala
    "dart"            // Dart
  ]
}
```

#### exclude_dirs

**Type**: Array of strings
**Default**: See complete list in Structure section above
**Purpose**: Directories to exclude from indexing

**Default List Includes**:
- Build outputs: node_modules, dist, build, target, bin, obj
- Version control: .git
- Virtual environments: venv, __pycache__
- IDE configs: .idea, .vscode, .gradle
- Test artifacts: coverage, .pytest_cache
- Framework outputs: .next, .nuxt
- CIDX internal: .code-indexer

**Customization**:
```json
{
  "exclude_dirs": [
    "node_modules", ".git", "__pycache__",
    "vendor",           // Add PHP vendor
    "Pods",             // Add iOS Pods
    "build-output"      // Custom build dir
  ]
}
```

**Include More**:
```json
{
  "exclude_dirs": [
    "node_modules", ".git",
    "test_data",        // Test fixtures
    "mock_apis",        // Mock data
    "legacy_code"       // Deprecated code
  ]
}
```

#### embedding_provider

**Type**: String
**Default**: "voyage-ai"
**Purpose**: Embedding provider selection

**Note**: Only "voyage-ai" is supported in v8.0+. This field exists for future extensibility but cannot be changed currently.

#### max_file_size

**Type**: Integer (bytes)
**Default**: 1048576 (1 MB)
**Purpose**: Maximum file size to index
**Location**: Nested under "indexing" object in config.json

**Customization**:
```json
{
  "indexing": {
    "max_file_size": 2097152  // 2 MB
  }
}
```

**Why Limit File Size?**:
- Large files increase indexing time
- Embedding API has token limits
- Quality degrades for very large files

**Recommendations**:
- **1 MB (default)**: Good for most code files
- **2-5 MB**: If you have larger source files
- **<500 KB**: If you want faster indexing

### Manual Editing

You can manually edit `.code-indexer/config.json`:

```bash
# Edit config
nano .code-indexer/config.json

# Reindex to apply changes
cidx index --clear
cidx index
```

**Important**: Changes take effect after re-indexing.

## Environment Variables

### Required

| Variable | Purpose | Example |
|----------|---------|---------|
| **VOYAGE_API_KEY** | VoyageAI API key | `export VOYAGE_API_KEY="your-api-key"` |

### Optional (Server Mode Only)

**Note**: These variables are ONLY used when running CIDX in server mode (multi-user deployment). They are NOT used in CLI or Daemon modes.

| Variable | Purpose | Default | Example |
|----------|---------|---------|---------|
| **CIDX_INDEX_CACHE_TTL_MINUTES** | Server cache TTL | 10 | `export CIDX_INDEX_CACHE_TTL_MINUTES=30` |
| **CIDX_SERVER_PORT** | Server port | 8000 | `export CIDX_SERVER_PORT=9000` |
| **CIDX_SERVER_HOST** | Server host | localhost | `export CIDX_SERVER_HOST=0.0.0.0` |

For CLI/Daemon mode configuration, use `cidx config` commands instead (see Daemon Mode section).

### Setting Environment Variables

**Linux/macOS**:
```bash
# Temporary (current session)
export VOYAGE_API_KEY="your-key"

# Permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export VOYAGE_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell)**:
```powershell
# Temporary (current session)
$env:VOYAGE_API_KEY = "your-key"

# Permanent (System Environment Variables)
# Control Panel → System → Advanced → Environment Variables
```

## Per-Project vs Global

### Per-Project Configuration

**Location**: `.code-indexer/` in each project
**Scope**: Single project only
**Use Case**: Project-specific settings

**Files**:
- `config.json` - Configuration
- `index/` - Vector indexes
- `scip/` - SCIP indexes

**Setup**:
```bash
cd /path/to/project
cidx index
# Creates .code-indexer/ in current directory
```

### Global Registry (Deprecated)

**Note**: The global registry (`~/.code-indexer/registry.json`) is **deprecated** since v8.0. CIDX no longer requires centralized registry for CLI/Daemon modes.

**Server Mode**: Still uses `~/.cidx-server/data/` for golden repositories, but this is server-specific, not a global registry.

## Advanced Configuration

### Daemon Mode

```bash
# Enable daemon mode
cidx config --daemon

# Disable daemon mode
cidx config --no-daemon

# Check current mode
cidx status
```

**What It Configures**:
- Enables background daemon process
- Activates in-memory caching
- Enables watch mode capability

### Watch Mode

```bash
# Start watch mode (requires daemon)
cidx watch

# Custom debounce
cidx watch --debounce 3.0

# With FTS indexing
cidx watch --fts
```

**Watch Mode Settings**:
- **Debounce**: Default 2.0 seconds (configurable via `--debounce`)
- **File monitoring**: Watches all files matching `file_extensions`
- **Excludes**: Respects `exclude_dirs` from config.json

### Language-Specific Indexing

Customize which languages to index by editing `file_extensions`:

```json
{
  "file_extensions": [
    ".py"              // Python only
  ]
}
```

Or use `--language` flag during queries:
```bash
cidx query "search" --language python
```

### Index Type Selection

```bash
# Semantic only (default)
cidx index

# Add full-text search
cidx index --fts

# Add git history
cidx index --index-commits

# All index types
cidx index --fts --index-commits

# SCIP code intelligence
cidx scip generate
```

## Troubleshooting

### API Key Not Found

**Error**: `ERROR: VOYAGE_API_KEY environment variable not set`

**Solutions**:

1. **Set environment variable**:
   ```bash
   export VOYAGE_API_KEY="your-key"
   ```

2. **Add to shell profile**:
   ```bash
   echo 'export VOYAGE_API_KEY="your-key"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. **Verify it's set**:
   ```bash
   echo $VOYAGE_API_KEY
   ```

### Config File Corrupted

**Error**: `ERROR: Invalid config.json`

**Solutions**:

1. **Delete and recreate**:
   ```bash
   rm .code-indexer/config.json
   cidx index
   # Creates fresh config.json with defaults
   ```

2. **Manually fix JSON**:
   ```bash
   nano .code-indexer/config.json
   # Fix JSON syntax errors
   ```

3. **Validate JSON**:
   ```bash
   python3 -m json.tool .code-indexer/config.json
   # Shows JSON syntax errors
   ```

### File Size Limit Too Restrictive

**Symptom**: Large files not indexed

**Solution**:
```json
{
  "max_file_size": 5242880  // Increase to 5 MB
}
```

Then reindex:
```bash
cidx index --clear
cidx index
```

### Excluded Directory Needed

**Symptom**: Important code in excluded directory not indexed

**Solution**:

1. **Edit config.json**:
   ```json
   {
     "exclude_dirs": [
       "node_modules", ".git"  // Removed "__pycache__"
     ]
   }
   ```

2. **Reindex**:
   ```bash
   cidx index --clear
   cidx index
   ```

### Wrong File Extensions

**Symptom**: Code files not being indexed

**Solution**:

1. **Add extensions to config.json**:
   ```json
   {
     "file_extensions": [
       ".py", ".js", ".ts",
       ".jsx", ".tsx"  // Add React extensions
     ]
   }
   ```

2. **Reindex**:
   ```bash
   cidx index
   ```

### Daemon Configuration Issues

**Problem**: Daemon mode not persisting

**Check**:
```bash
# Verify daemon mode enabled
cidx status

# Re-enable if needed
cidx config --daemon
cidx start
```

---

