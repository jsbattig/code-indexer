# Code Indexer

AI-powered semantic code search for your codebase. Find code by meaning, not just keywords.

## Features

- **Semantic Search** - Find code by meaning using vector embeddings and AST-based semantic chunking
- **Multiple Providers** - Local (Ollama) or cloud (VoyageAI) embeddings  
- **Smart Indexing** - Incremental updates, git-aware, multi-project support
- **Semantic Filtering** - Filter by code constructs (classes, functions), scope, language features
- **Multi-Language Support** - AST parsing for Python, JavaScript, TypeScript, Java, Go, Kotlin
- **CLI Interface** - Simple commands with progress indicators
- **AI Analysis** - Integrates with Claude CLI for code analysis with semantic search
- **Privacy Options** - Full local processing or cloud for better performance

## Installation

### pipx (Recommended)
```bash
pipx install git+https://github.com/jsbattig/code-indexer.git
```

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
