# Code Indexer

AI-powered semantic code search for your codebase. Find code by meaning, not just keywords.

## Features

- **Semantic Search** - Find code by meaning using vector embeddings and AST-based semantic chunking
- **Multiple Providers** - Local (Ollama) or cloud (VoyageAI) embeddings  
- **Smart Indexing** - Incremental updates, git-aware, multi-project support
- **Semantic Filtering** - Filter by code constructs (classes, functions), scope, language features
- **Multi-Language Support** - AST parsing for Python, JavaScript, TypeScript, Java, C#, Go, Kotlin, Groovy, Pascal/Delphi, SQL, C, C++, Rust, Swift, Ruby, Lua, HTML, CSS, YAML, XML
- **CLI Interface** - Simple commands with progress indicators
- **AI Analysis** - Integrates with Claude CLI for code analysis with semantic search
- **Privacy Options** - Full local processing or cloud for better performance

## Installation

### pipx (Recommended)
```bash
# Install the package
pipx install git+https://github.com/jsbattig/code-indexer.git

# Setup global registry (standalone command - requires sudo)
cidx setup-global-registry
```

### pip with virtual environment
```bash
python3 -m venv code-indexer-env
source code-indexer-env/bin/activate
pip install git+https://github.com/jsbattig/code-indexer.git

# Setup global registry (standalone command - requires sudo)
code-indexer setup-global-registry
```

### Requirements

- **Python 3.9+**
- **Container Engine**: Docker or Podman (for containerized services)
- **Memory**: 4GB+ RAM recommended
- **Disk Space**: ~500MB for base containers + vector data storage

### Docker vs Podman Support

Code Indexer supports both Docker and Podman container engines:

- **Auto-detection**: Automatically detects and uses available container engine
- **Podman preferred**: Uses Podman by default when available (better rootless support)
- **Force Docker**: Use `--force-docker` flag to force Docker usage
- **Rootless containers**: Fully supports rootless container execution

**Global Port Registry**: The `setup-global-registry` command configures system-wide port coordination at `/var/lib/code-indexer/port-registry`, preventing conflicts when running multiple code-indexer projects simultaneously. This is required for proper multi-project support.

## Quick Start

```bash
# 1. Setup global registry (once per system)
cidx setup-global-registry

# 2. Navigate to your project
cd /path/to/your/project

# 3. Start services and index code
code-indexer start     # Auto-creates config if needed
code-indexer index     # Smart incremental indexing

# 4. Search semantically
code-indexer query "authentication logic"

# 5. Search with semantic filtering
code-indexer query "user" --type class --scope global
code-indexer query "save" --features async --language python

# 6. AI-powered analysis (requires Claude CLI)
code-indexer claude "How does auth work in this app?"
```

### Alternative: Custom Configuration

```bash
# Optional: Initialize with custom settings first
code-indexer init --embedding-provider voyage-ai --max-file-size 2000000
code-indexer start
code-indexer index
```

## Complete CLI Reference

### Setup Commands

```bash
# Global system setup
code-indexer setup-global-registry              # Setup global port registry (requires sudo)
code-indexer setup-global-registry --test-access --quiet  # Test registry access

# Project initialization
code-indexer init                               # Initialize with default settings
code-indexer init --embedding-provider voyage-ai  # Use VoyageAI instead of Ollama
code-indexer init --max-file-size 2000000       # Set 2MB file size limit
code-indexer init --setup-global-registry       # Init + setup registry (legacy)
code-indexer init --create-override-file        # Create .code-indexer-override.yaml
```

### Service Management

```bash
# Service lifecycle
code-indexer start                      # Start services (smart detection)
code-indexer start --force-docker       # Force Docker instead of Podman
code-indexer start --force-recreate     # Force recreate containers
code-indexer start --quiet              # Silent mode
code-indexer start -m all-minilm-l6-v2  # Different Ollama model

code-indexer status                     # Check service status
code-indexer status --force-docker      # Check Docker status specifically

code-indexer stop                       # Stop services (preserve data)
code-indexer stop --force-docker        # Stop Docker services specifically
```

### Indexing Commands

```bash
# Standard indexing
code-indexer index                      # Smart incremental indexing
code-indexer index --clear              # Force full reindex
code-indexer index --reconcile          # Reconcile disk vs database
code-indexer index --detect-deletions   # Handle deleted files
code-indexer index --batch-size 25      # Custom batch size
code-indexer index --files-count-to-process 100  # Limit file count
code-indexer index --threads 4          # Custom thread count

# Real-time monitoring
code-indexer watch                      # Git-aware file watching
code-indexer watch --debounce 5.0       # Custom debounce delay
code-indexer watch --initial-sync       # Full sync before watching
```

### Search Commands

```bash
# Basic search
code-indexer query "search terms"      # Semantic search
code-indexer query "auth" --limit 20   # More results
code-indexer query "function" --quiet  # Only results, no headers

# Advanced filtering
code-indexer query "user" --language python  # Filter by language
code-indexer query "save" --path "*/models/*" # Filter by path pattern
code-indexer query "class" --type class       # Filter by code construct
code-indexer query "async" --features async   # Filter by language feature
code-indexer query "auth" --scope global      # Filter by scope
code-indexer query "function" --semantic-only # Only semantic chunks
code-indexer query "test" --min-score 0.8     # High-confidence matches

# Short alias
cidx query "search terms"              # Same as code-indexer query
```

### AI Analysis Commands

```bash
# Standard analysis
code-indexer claude "How does auth work?"     # AI-powered analysis
code-indexer claude "Debug this" --limit 15   # Custom search limit
code-indexer claude "Analyze" --context-lines 200  # More context
code-indexer claude "Quick check" --quiet     # Minimal output
code-indexer claude "Review code" --no-stream # No streaming output

# Advanced options
code-indexer claude "Test" --include-file-list  # Include project file list
code-indexer claude "Legacy" --rag-first       # Use legacy RAG-first approach

# Debugging
code-indexer claude "Test" --dry-run-show-claude-prompt  # Show prompt without execution
code-indexer claude "Analyze" --show-claude-plan        # Show tool usage tracking
```

### Data Management Commands

```bash
# Quick cleanup (recommended)
code-indexer clean-data                 # Clear current project data
code-indexer clean-data --all-projects  # Clear all projects data
code-indexer clean-data --force-docker  # Use Docker for cleanup

# Complete removal
code-indexer uninstall                  # Remove current project completely
code-indexer uninstall --force-docker   # Use Docker for removal
code-indexer uninstall --wipe-all       # DANGEROUS: Complete system wipe

# Migration and maintenance
code-indexer clean-legacy               # Migrate from legacy containers
code-indexer optimize                   # Optimize vector database
code-indexer force-flush                # Force flush to disk (deprecated)
code-indexer force-flush --collection mycoll  # Flush specific collection
```

### Configuration Commands

```bash
# Configuration repair
code-indexer fix-config                 # Fix corrupted configuration
code-indexer fix-config --dry-run       # Preview fixes
code-indexer fix-config --verbose       # Detailed fix information
code-indexer fix-config --force         # Apply without confirmation

# Claude integration setup
code-indexer set-claude-prompt          # Set CIDX instructions in project CLAUDE.md
code-indexer set-claude-prompt --user-prompt  # Set in global ~/.claude/CLAUDE.md
```

### Global Options

```bash
# Available on most commands
--force-docker          # Force Docker instead of Podman
--verbose, -v           # Verbose output
--config, -c PATH       # Custom config file path
--path, -p PATH         # Custom project directory

# Special global options
--use-cidx-prompt       # Generate AI integration prompt
--format FORMAT         # Output format (text, markdown, compact, comprehensive)
--output FILE           # Save output to file
--compact               # Generate compact prompt
```

### Command Aliases

- `cidx` → `code-indexer` (shorter alias for all commands)
- Use `cidx` for faster typing: `cidx start`, `cidx query "search"`, etc.

## Configuration

### Embedding Providers

**Ollama (Default - Local)**
```bash
code-indexer init --embedding-provider ollama
```

**VoyageAI (Cloud)**
```bash
export VOYAGE_API_KEY="your-key"
code-indexer init --embedding-provider voyage-ai
```

**Performance Status Indicators (VoyageAI only)**

During indexing, VoyageAI shows real-time performance status in the progress bar:
- ⚡ **Full speed** - Running at maximum throughput
- 🟡 **CIDX throttling** - Internal rate limiter active
- 🔴 **Server throttling** - VoyageAI API rate limits detected, automatically backing off

Example: `15/100 files (15%) | 8.3 emb/s ⚡ | 8 threads | main.py`

The system runs at full speed by default and only backs off when rate limits are encountered.

### Configuration File
Configuration is stored in `.code-indexer/config.json`:
- `file_extensions`: File types to index
- `exclude_dirs`: Directories to skip  
- `chunk_size`: Text chunk size
- `embedding_provider`: ollama or voyage-ai
- `use_semantic_chunking`: Enable AST-based semantic chunking (default: true)
- `max_file_size`: Maximum file size in bytes (default: 1MB)

## Supported Languages

Code Indexer provides AST-based semantic chunking for comprehensive code understanding:

| Language | File Extensions | Semantic Features |
|----------|----------------|-------------------|
| **Python** | `.py` | Classes, functions, methods, decorators, async/await |
| **JavaScript** | `.js`, `.jsx` | Classes, functions, arrow functions, async/await, JSX |
| **TypeScript** | `.ts`, `.tsx` | Interfaces, types, generics, decorators, JSX |
| **Java** | `.java` | Classes, interfaces, methods, annotations, generics |
| **C#** | `.cs` | Classes, interfaces, methods, properties, namespaces, attributes |
| **Go** | `.go` | Structs, interfaces, functions, methods, goroutines |
| **Kotlin** | `.kt`, `.kts` | Classes, data classes, objects, extension functions |
| **Groovy** | `.groovy`, `.gradle`, `.gvy`, `.gy` | Classes, traits, closures, DSL patterns, Gradle scripts |
| **Pascal/Delphi** | `.pas`, `.pp`, `.dpr`, `.dpk`, `.inc` | Units, classes, procedures, functions, properties |
| **SQL** | `.sql` | Tables, views, indexes, procedures, functions, triggers, CTEs |
| **C** | `.c`, `.h` | Structs, unions, functions, enums, typedefs, preprocessor directives |
| **C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` | Classes, templates, namespaces, operators, inheritance, RAII |
| **Rust** | `.rs` | Structs, enums, traits, impl blocks, functions, modules, lifetimes |
| **Swift** | `.swift` | Classes, structs, protocols, extensions, enums, generics, property wrappers |
| **Ruby** | `.rb`, `.rake`, `.gemspec` | Classes, modules, methods, blocks, mixins, metaprogramming |
| **Lua** | `.lua` | Functions, tables, modules, methods, local/global scope |
| **HTML** | `.html`, `.htm` | Elements, attributes, scripts, styles, comments, document structure |
| **CSS** | `.css`, `.scss`, `.sass` | Selectors, rules, media queries, at-rules, animations, variables |
| **YAML** | `.yaml`, `.yml` | Mappings, sequences, anchors, aliases, multi-document |
| **XML** | `.xml`, `.xsd`, `.xsl`, `.xslt` | Elements, attributes, namespaces, CDATA, processing instructions |

All parsers include robust ERROR node handling to extract meaningful constructs even from malformed code.

### Containerized Services

Code Indexer uses the following containerized services:

- **Qdrant**: Vector database for storing code embeddings
- **Ollama** (optional): Local language model service for embeddings when not using VoyageAI
- **Data Cleaner**: Containerized service for cleaning root-owned files during data removal operations

## Development

```bash
git clone https://github.com/jsbattig/code-indexer.git
cd code-indexer
pip install -e ".[dev]"
pytest
```

## License

MIT License

## Contributing

Issues and pull requests welcome!
