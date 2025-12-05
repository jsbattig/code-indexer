# Code Indexer (`cidx`)

AI-powered semantic code search for your codebase. Find code by meaning, not just keywords.

**Version 8.0.0** - [Changelog](CHANGELOG.md) | [Migration Guide](docs/migration-to-v8.md) | [Architecture](docs/architecture.md)

## CIDX MCP Bridge for Claude Desktop

Connect Claude Desktop to your CIDX server for semantic code search directly in conversations.

### Quick Setup (3 Steps)

**Step 1: Run Setup Script (creates config file)**

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/jsbattig/code-indexer/master/scripts/setup-mcpb.sh)"
```

This will prompt you for:
- Server URL (e.g., `https://your-server.com:8383`)
- Username
- Password

It creates `~/.mcpb/config.json` with your authentication tokens.

**Step 2: Download MCPB Binary**

Download for your platform from [GitHub Releases](https://github.com/jsbattig/code-indexer/releases/latest):

- macOS (Apple Silicon): `mcpb-darwin-arm64`
- macOS (Intel): `mcpb-darwin-x64`
- Linux: `mcpb-linux-x64`
- Windows: `mcpb-windows-x64.exe`

Make executable (macOS/Linux):
```bash
chmod +x /path/to/mcpb-darwin-arm64
```

**Step 3: Configure Claude Desktop**

Edit configuration file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Add this configuration:
```json
{
  "mcpServers": {
    "cidx": {
      "command": "/absolute/path/to/mcpb-darwin-arm64"
    }
  }
}
```

Replace `/absolute/path/to/mcpb-darwin-arm64` with the actual path to your downloaded binary.

**Restart Claude Desktop** to activate the MCP server.

### Token Management

Token refresh is fully automatic. MCPB transparently refreshes expired tokens using stored credentials - no cron jobs or manual intervention required.

### Features
- **Full Query Parity**: All 25 search_code parameters available
- **SSE Streaming**: Progressive results for large queries
- **Multi-Platform**: macOS (Intel/Apple Silicon), Linux, Windows
- **Zero Dependencies**: Single binary, no Python runtime required
- **Complete Documentation**: 4,000+ lines covering setup, API, queries, troubleshooting

### Documentation
- [Setup Guide](docs/mcpb/setup.md) - Detailed installation and configuration
- [API Reference](docs/mcpb/api-reference.md) - All 22 MCP tools
- [Query Guide](docs/mcpb/query-guide.md) - Search capabilities
- [Troubleshooting](docs/mcpb/troubleshooting.md) - Common issues

## Quick Install

### pipx (Recommended)
```bash
# Install the package
pipx install git+https://github.com/jsbattig/code-indexer.git@v8.0.0

# Setup global registry (required once per system)
cidx setup-global-registry

# If cidx command is not found, add pipx bin directory to PATH:
# export PATH="$HOME/.local/bin:$PATH"
```

### pip with virtual environment
```bash
python3 -m venv code-indexer-env
source code-indexer-env/bin/activate
pip install git+https://github.com/jsbattig/code-indexer.git@v8.0.0

# Setup global registry
cidx setup-global-registry
```

**Requirements**: Python 3.9+, 4GB+ RAM

## Quick Start

```bash
# Navigate to your project
cd /path/to/your/project

# Start services and index code
cidx start     # Auto-creates config if needed
cidx index     # Smart incremental indexing

# Search semantically
cidx query "authentication logic"

# Search with filtering
cidx query "user" --language python --min-score 0.7
cidx query "save" --path-filter "*/models/*" --limit 20
```

## Key Features

### Three Search Modes

**1. Semantic Search (Default)** - Find code by meaning using AI embeddings
```bash
cidx query "authentication logic"
cidx query "database connection setup"
```

**2. Full-Text Search (--fts)** - Fast, exact text matching (1.36x faster than grep)
```bash
cidx query "authenticate_user" --fts
cidx query "ParseError" --fts --case-sensitive
cidx query "authenticte" --fts --fuzzy  # Typo tolerant
```

**3. Regex Pattern Matching (--fts --regex)** - Token-based patterns (10-50x faster than grep)
```bash
cidx query "def" --fts --regex                    # Find function definitions
cidx query "test_.*" --fts --regex --language python  # Find test functions
```

### Git History Search

Search your entire commit history semantically:
```bash
# Index git history
cidx index --index-commits

# Search historical commits
cidx query "JWT authentication" --time-range-all --quiet

# Search specific time period
cidx query "bug fix" --time-range 2024-01-01..2024-12-31 --quiet

# Filter by author
cidx query "login" --time-range-all --author "john@example.com" --quiet
```

**Use Cases**: Code archaeology, bug history, feature evolution tracking, author analysis

### Performance

- **HNSW indexing**: 300x faster queries (~20ms vs 6+ seconds)
- **Incremental updates**: 3.6x speedup for re-indexing
- **Watch mode**: <20ms per file change
- **FTS**: 1.36x faster than grep on indexed codebases
- **Server-side caching**: 100-1800x speedup for repeated queries (277ms to <1ms)

### Advanced Filtering

```bash
# Language filtering
cidx query "authentication" --language python

# Path filtering
cidx query "models" --path-filter "*/src/*"

# Exclude patterns
cidx query "production code" --exclude-path "*/tests/*"

# Exclude languages
cidx query "api handlers" --exclude-language javascript --exclude-language css

# Combine filters
cidx query "database models" \
  --language python \
  --path-filter "*/src/*" \
  --exclude-path "*/tests/*" \
  --min-score 0.8
```

### Real-Time Watch Mode

```bash
# Watch for file changes and auto-index
cidx watch --fts

# With custom debounce delay
cidx watch --debounce 5.0
```

### AI Platform Integration

**Local CLI Integration**: Teach AI assistants to use semantic search via CLI:
```bash
# Install instructions for Claude Code
cidx teach-ai --claude --project    # Creates ./CLAUDE.md

# Global installation
cidx teach-ai --claude --global     # Creates ~/.claude/CLAUDE.md

# Other platforms
cidx teach-ai --gemini --project
cidx teach-ai --codex --global
```

**Remote MCP Server Integration**: Connect AI assistants to CIDX server for team-wide semantic search:
- **MCP Protocol 2024-11-05** - Standard Model Context Protocol implementation
- **OAuth 2.0 Authentication** - Secure AI assistant authentication via browser flow
- **Remote Code Search** - AI tools query centralized indexed codebases
- **Permission Controls** - Role-based access (admin, power_user, normal_user)
- **Golden Repository Access** - Query team's shared code repositories

```bash
# Configure Claude Code to connect to CIDX MCP server
# Add to Claude Code MCP settings (see docs/v5.0.0-architecture-summary.md for server setup)
```

## Two Operating Modes

### CLI Mode (Individual Developers)

Direct command-line interface for local development:
- Direct CLI commands: `cidx init`, `cidx index`, `cidx query`
- Local project indexing in `.code-indexer/`
- Container-free filesystem storage
- Instant setup, no dependencies
- Real-time progress tracking

### Daemon Mode (Performance)

Background service for faster queries:
- In-memory index caching (~5ms queries vs ~1s from disk)
- Watch mode for real-time file change indexing
- Unix socket communication
- Container-free, runs as local process

```bash
# Enable and start daemon
cidx config --daemon
cidx start

# Use watch mode for real-time updates
cidx watch
```

### Server Mode (Team Collaboration)

Multi-user server with advanced caching for team-wide semantic search:
- **Automatic HNSW index caching**: 100-1800x speedup for repeated queries
- **First query (cold)**: ~277ms (OS page cache benefit)
- **Subsequent queries (warm)**: <1ms (in-memory cache)
- **TTL-based eviction**: Configurable cache lifetime (default: 10 minutes)
- **Per-repository isolation**: Independent cache entries for each repository
- **Multi-user support**: Shared cache across team members
- **OAuth 2.0 authentication**: Secure access control

**Cache Configuration**:
```bash
# Configure cache TTL (seconds)
export CIDX_HNSW_CACHE_TTL_SECONDS=600  # 10 minutes default

# Server mode auto-enabled when running server
```

**Monitor Cache Performance**:
```bash
# Query cache statistics
curl http://localhost:8000/cache/stats

# Response shows hit/miss ratios and speedup metrics
{
  "total_hits": 1234,
  "total_misses": 56,
  "hit_ratio": 0.957,
  "active_entries": 12
}
```

See [Server Deployment Guide](docs/server-deployment.md) for detailed configuration.

## Common Commands

```bash
# Service management
cidx start                          # Start services
cidx stop                           # Stop services
cidx status                         # Check status

# Indexing
cidx index                          # Incremental indexing
cidx index --fts                    # Index with full-text search
cidx index --clear                  # Force full reindex
cidx index --index-commits          # Index git history

# Searching
cidx query "search terms"           # Semantic search
cidx query "text" --fts             # Full-text search
cidx query "pattern" --fts --regex  # Regex search
cidx query "code" --fts --semantic  # Hybrid search

# For complete parameter reference (23 query parameters)
# See: src/code_indexer/query/QUERY_PARAMETERS.md

# Watch mode
cidx watch                          # Real-time file watching
cidx watch --fts                    # Watch with FTS updates

# Data management
cidx clean-data                     # Clear current project data
cidx uninstall                      # Remove current project
```

## Supported Languages

Python, JavaScript, TypeScript, Java, C#, C, C++, Go, Rust, Kotlin, Swift, Ruby, PHP, Lua, Groovy, Pascal/Delphi, SQL, HTML, CSS, YAML, XML, and more.

See [Technical Details - Supported Languages](docs/technical-details.md#supported-languages) for complete language support details.

## Configuration

### Embedding Provider

Code-indexer uses **VoyageAI embeddings** (cloud-based API). This is the only supported embedding provider in v8.0+.

```bash
export VOYAGE_API_KEY="your-key"
cidx init  # VoyageAI is automatically used
```

Get your API key from: https://www.voyageai.com/

### Vector Storage Backend

Code-indexer uses **filesystem backend** (container-free, local storage). This is the only supported backend in v8.0+.

```bash
cidx init  # Filesystem backend is automatically used
```

Vector data is stored in `.code-indexer/index/` as optimized JSON files.

### Configuration File

Configuration stored in `.code-indexer/config.json`:
- `file_extensions`: File types to index
- `exclude_dirs`: Directories to skip
- `embedding_provider`: "voyage-ai" (only supported provider)
- `max_file_size`: Maximum file size (default: 1MB)

## Documentation

- **[Changelog](CHANGELOG.md)** - Version history and release notes
- **[Migration Guide](docs/migration-to-v8.md)** - Upgrading from v7.x to v8.0
- **[Architecture](docs/architecture.md)** - System design and technical decisions
- **[Technical Details](docs/technical-details.md)** - Deep dives into algorithms and implementation
- **[Algorithms](docs/algorithms.md)** - Detailed algorithm descriptions and complexity analysis

## Development

```bash
# Clone repository
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer
pip install -e ".[dev]"

# Run tests
./ci-github.sh              # Fast tests (~6-7 min)
./full-automation.sh        # Comprehensive tests (~10+ min)

# Linting
./lint.sh                   # ruff, black, mypy
```

For detailed testing infrastructure and contribution guidelines, see the project documentation.

## License

MIT License

## Contributing

Issues and pull requests welcome! Please follow the testing guidelines in the project documentation and ensure all tests pass before submitting PRs.
