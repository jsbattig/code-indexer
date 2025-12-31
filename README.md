# Code Indexer (`cidx`)

AI-powered semantic code search for your codebase. Find code by meaning, not just keywords.

**Version 8.4.46** - [Changelog](CHANGELOG.md) | [Migration Guide](docs/migration-to-v8.md) | [Architecture](docs/architecture.md)

## Quick Navigation

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Key Features](#key-features)
- [Operating Modes](#operating-modes)
- [Common Commands](#common-commands)
- [Documentation](#documentation)

## What is CIDX?

CIDX combines semantic embeddings with traditional search to help you find code by meaning, not just keywords. Search your codebase with natural language queries like "authentication logic" or "database connection setup", trace symbol references with SCIP code intelligence, and explore git history semantically.

## Installation

### pipx (Recommended)

```bash
pipx install git+https://github.com/jsbattig/code-indexer.git@v8.4.46

# Verify installation
cidx --version
```

### pip with virtual environment

```bash
python3 -m venv code-indexer-env
source code-indexer-env/bin/activate
pip install git+https://github.com/jsbattig/code-indexer.git@v8.4.46
```

**Requirements**: Python 3.9+, 4GB+ RAM, VoyageAI API key

For detailed installation instructions including Windows, configuration, and troubleshooting, see [Installation Guide](docs/installation.md).

## Quick Start

```bash
# Navigate to your project
cd /path/to/your/project

# Set VoyageAI API key (required for semantic search)
export VOYAGE_API_KEY="your-api-key-here"

# Index your codebase
cidx index

# Search semantically
cidx query "authentication logic" --limit 5

# Search with filters
cidx query "user" --language python --min-score 0.7
cidx query "save" --path-filter "*/models/*" --limit 10
```

For comprehensive query options and search strategies, see [Query Guide](docs/query-guide.md).

## Key Features

### Semantic Search

Find code by meaning using AI embeddings powered by VoyageAI. Ask natural language questions and get semantically relevant results ranked by similarity.

```bash
cidx query "authentication logic" --limit 10
cidx query "database connection setup" --language python
```

See: [Query Guide](docs/query-guide.md)

### Full-Text Search (FTS)

Fast exact text matching with fuzzy search, regex support, and case sensitivity options. Up to 50x faster than grep with indexed searching.

```bash
cidx query "authenticate_user" --fts
cidx query "ParseError" --fts --case-sensitive
cidx query "test_.*" --fts --regex --language python
```

See: [Query Guide](docs/query-guide.md#full-text-search-fts)

### SCIP Code Intelligence

Precise code navigation using SCIP (Source Code Intelligence Protocol). Find symbol definitions, references, dependencies, dependents, call chains, and perform impact analysis.

```bash
cidx scip generate                    # Generate SCIP indexes
cidx scip definition "UserService"    # Find definition
cidx scip references "authenticate"   # Find all usages
cidx scip callchain "main" "login"    # Trace execution path
cidx scip impact "DatabaseManager"    # Impact analysis
```

See: [SCIP Code Intelligence Guide](docs/scip/README.md)

### Git History Search (Temporal)

Search your entire commit history semantically. Find when code was added, modified, or deleted with time-range filtering, author filtering, and diff type selection.

```bash
cidx index --index-commits                # Index git history (one-time)
cidx query "JWT auth" --time-range-all    # Search all history
cidx query "bug fix" --time-range 2024-01-01..2024-12-31
cidx query "login" --time-range-all --author "john@example.com"
```

See: [Temporal Search Guide](docs/temporal-search.md)

### Real-Time Watch Mode

Monitor file changes and automatically re-index in real-time with daemon mode. Get ~5ms cached queries versus ~1s from disk.

```bash
cidx config --daemon    # Enable daemon mode
cidx start              # Start daemon
cidx watch              # Start watch mode
cidx query "search"     # Fast cached queries
```

See: [Operating Modes Guide](docs/operating-modes.md#daemon-mode)

### AI Integration

Connect AI assistants to CIDX for semantic search directly in conversations. Supports local CLI integration (Claude Code, Gemini, Codex) and remote MCP server integration (Claude Desktop).

```bash
# Local CLI integration
cidx teach-ai --claude --project    # Creates CLAUDE.md

# Remote MCP server for Claude Desktop
# See MCP Bridge guide for setup
```

See: [AI Integration Guide](docs/ai-integration.md) | [MCP Bridge Guide](docs/mcpb/README.md)

## Operating Modes

CIDX operates in two modes optimized for different use cases:

### CLI Mode (Individual Developers)

Direct command-line interface for local development with instant setup and no dependencies.

```bash
cidx init      # Create .code-indexer/
cidx index     # Index codebase
cidx query     # Search (~1s per query from disk)
```

### Daemon Mode (Performance)

Background service with in-memory caching for faster queries (~5ms) and real-time watch mode.

```bash
cidx config --daemon    # Enable daemon
cidx start              # Start daemon
cidx query "search"     # Fast cached queries
cidx watch              # Real-time indexing
```

For server mode (team collaboration with centralized golden repositories), see [Operating Modes Guide](docs/operating-modes.md).

## Common Commands

### Indexing

```bash
cidx init                    # Create .code-indexer/ config
cidx index                   # Semantic indexing (default)
cidx index --fts             # Add full-text search
cidx index --index-commits   # Add git history indexing
cidx scip generate           # Generate SCIP indexes
```

### Querying

```bash
# Semantic search
cidx query "search term" --limit 10

# Full-text search
cidx query "exact text" --fts

# Regex pattern matching
cidx query "pattern" --fts --regex

# Git history search
cidx query "term" --time-range-all --quiet

# SCIP code intelligence
cidx scip definition "Symbol"
cidx scip references "function_name"
```

### Filtering

```bash
--language python           # Filter by language
--path-filter "*/tests/*"   # Filter by path pattern
--exclude-path "*/vendor/*" # Exclude paths
--min-score 0.8             # Minimum similarity score
--limit 20                  # Max results
```

### Daemon Mode

```bash
cidx config --daemon        # Enable daemon
cidx start                  # Start daemon
cidx stop                   # Stop daemon
cidx status                 # Check status
cidx watch                  # Start watch mode
cidx watch-stop             # Stop watch mode
```

## Configuration

CIDX requires minimal configuration. The VoyageAI API key is the only required setting.

### VoyageAI API Key (Required)

```bash
# Add to shell profile (~/.bashrc or ~/.zshrc)
export VOYAGE_API_KEY="your-api-key-here"
source ~/.bashrc
```

### Project Configuration

CIDX auto-creates `.code-indexer/config.json` on first run with sensible defaults. You can customize:

- `file_extensions` - File types to index
- `exclude_dirs` - Directories to skip
- `max_file_size` - Maximum file size (default 1MB)

For complete configuration reference including environment variables, daemon settings, and watch mode options, see [Configuration Guide](docs/configuration.md).

## Documentation

### Getting Started
- [Installation Guide](docs/installation.md) - Complete installation for all platforms
- [Query Guide](docs/query-guide.md) - All 23 query parameters and search strategies
- [Configuration Guide](docs/configuration.md) - VoyageAI setup, config options, environment variables

### Features
- [SCIP Code Intelligence](docs/scip/README.md) - Symbol navigation, dependencies, call chains
- [Temporal Search](docs/temporal-search.md) - Git history search with time-range filtering
- [Operating Modes](docs/operating-modes.md) - CLI, Daemon, Server modes explained

### AI Integration
- [AI Integration Guide](docs/ai-integration.md) - Connect AI assistants to CIDX
- [MCP Bridge Guide](docs/mcpb/README.md) - Claude Desktop integration via MCP

### Advanced
- [Architecture Guide](docs/architecture.md) - System design and storage architecture
- [Migration Guide](docs/migration-to-v8.md) - Upgrading from v7.x to v8.x
- [Changelog](CHANGELOG.md) - Version history and release notes

## Contributing

Contributions welcome! Please see the [GitHub Issues](https://github.com/jsbattig/code-indexer/issues) page to report bugs or suggest features.

## License

MIT License - See repository for full license text.

---

**Support**: [GitHub Issues](https://github.com/jsbattig/code-indexer/issues)
**Repository**: [https://github.com/jsbattig/code-indexer](https://github.com/jsbattig/code-indexer)
