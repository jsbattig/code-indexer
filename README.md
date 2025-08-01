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

# Setup global registry (required for multi-project coordination)
cidx init --setup-global-registry
```

**Note**: The `--setup-global-registry` flag configures system-wide port coordination, preventing conflicts when running multiple code-indexer projects simultaneously.

### pip with virtual environment
```bash
python3 -m venv code-indexer-env
source code-indexer-env/bin/activate
pip install git+https://github.com/jsbattig/code-indexer.git
```

## Quick Start

```bash
# Navigate to your project
cd /path/to/your/project

# Initialize with global registry setup (first time only)
cidx init --setup-global-registry

# Start services and index code
code-indexer start
code-indexer index

# Search semantically
code-indexer query "authentication logic"

# Search with semantic filtering
code-indexer query "user" --type class --scope global
code-indexer query "save" --features async --language python

# AI-powered analysis (requires Claude CLI)
code-indexer claude "How does auth work in this app?"
```

## Commands

```bash
# Core commands
code-indexer start                    # Start services (Ollama + Qdrant)
code-indexer index                    # Index codebase (smart incremental)
code-indexer query "search terms"    # Semantic search
code-indexer claude "analyze this"   # AI-powered analysis
code-indexer status                   # Check service status
code-indexer stop                     # Stop services

# Claude Code integration
code-indexer set-claude-prompt        # Set CIDX instructions in project CLAUDE.md
code-indexer set-claude-prompt --user-prompt  # Set in global ~/.claude/CLAUDE.md

# Additional options
code-indexer index --clear            # Force full reindex
code-indexer index --reconcile        # Reconcile disk vs database
code-indexer query "auth" --limit 20  # More results
code-indexer query "function" --type function --semantic-only  # Semantic filtering
code-indexer watch                    # Real-time updates
cidx query "search"                   # Short alias
```

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

## Requirements

- Python 3.8+
- Docker (for Ollama/Qdrant services)
- 4GB+ RAM recommended

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
