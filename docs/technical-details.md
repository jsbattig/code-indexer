# Technical Details

This document provides deep technical information about Code Indexer implementation details, CLI reference, and advanced usage patterns.

## Complete CLI Reference

### Setup Commands

```bash
# Global system setup
cidx setup-global-registry              # Setup global port registry (requires sudo)
cidx setup-global-registry --test-access --quiet  # Test registry access

# Project initialization
cidx init                               # Initialize with default settings
cidx init --embedding-provider voyage-ai  # Use VoyageAI
cidx init --max-file-size 2000000       # Set 2MB file size limit
cidx init --setup-global-registry       # Init + setup registry (legacy)
cidx init --create-override-file        # Create .code-indexer-override.yaml
```

### Service Management

```bash
# Service lifecycle
cidx start                      # Start services (smart detection)
cidx start --quiet              # Silent mode

cidx status                     # Check service status

cidx stop                       # Stop services (preserve data)
```

### Indexing Commands

```bash
# Standard indexing
cidx index                      # Smart incremental indexing
cidx index --fts                # Index with full-text search
cidx index --clear              # Force full reindex
cidx index --reconcile          # Reconcile disk vs database
cidx index --detect-deletions   # Handle deleted files
cidx index --batch-size 25      # Custom batch size
cidx index --files-count-to-process 100  # Limit file count
cidx index --threads 8          # Custom thread count (configure in config.json)

# Git history indexing
cidx index --index-commits              # Index git history
cidx index --index-commits --all-branches  # All branches
cidx index --index-commits --max-commits 1000  # Limit commits
cidx index --index-commits --since-date 2024-01-01  # Recent commits only

# Real-time monitoring
cidx watch                      # Git-aware file watching
cidx watch --fts                # Watch with FTS updates
cidx watch --debounce 5.0       # Custom debounce delay
cidx watch --initial-sync       # Full sync before watching
cidx watch-stop                 # Stop watch mode
```

### Search Commands

```bash
# Basic semantic search
cidx query "search terms"      # Semantic search
cidx query "auth" --limit 20   # More results
cidx query "function" --quiet  # Only results, no headers

# Full-text search
cidx query "authenticate_user" --fts  # Exact text match
cidx query "ParseError" --fts --case-sensitive  # Case-sensitive
cidx query "authenticte" --fts --fuzzy  # Fuzzy matching
cidx query "conection" --fts --edit-distance 2  # Custom fuzzy distance

# Regex search
cidx query "def" --fts --regex  # Token-based regex
cidx query "test_.*" --fts --regex --language python  # Filtered regex
cidx query "TODO" --fts --regex  # Case-insensitive by default

# Hybrid search
cidx query "login" --fts --semantic  # Both modes in parallel

# Advanced filtering
cidx query "user" --language python  # Filter by language
cidx query "save" --path-filter "*/models/*" # Filter by path pattern
cidx query "function" --min-score 0.7  # Higher confidence matches
cidx query "database" --limit 15     # More results
cidx query "test" --exclude-path "*/tests/*"  # Exclude paths
cidx query "api" --exclude-language javascript  # Exclude languages

# Git history search
cidx query "JWT authentication" --time-range-all --quiet
cidx query "bug fix" --time-range 2024-01-01..2024-12-31 --quiet
cidx query "login" --time-range-all --chunk-type commit_message --quiet
cidx query "function" --time-range-all --chunk-type commit_diff --quiet
cidx query "api" --time-range-all --author "john@example.com" --quiet
```

### Language Filtering

CIDX supports intelligent language filtering with comprehensive file extension mapping:

```bash
# Friendly language names (recommended)
cidx query "authentication" --language python     # Matches .py, .pyw, .pyi files
cidx query "components" --language javascript     # Matches .js, .jsx files
cidx query "models" --language typescript         # Matches .ts, .tsx files
cidx query "handlers" --language cpp              # Matches .cpp, .cc, .cxx, .c++ files

# Direct extension usage (also supported)
cidx query "function" --language py               # Matches only .py files
cidx query "component" --language jsx             # Matches only .jsx files
```

**Supported Languages**: python, javascript, typescript, java, csharp, c, cpp, go, rust, php, ruby, swift, kotlin, scala, dart, html, css, vue, markdown, xml, yaml, json, sql, shell, bash, dockerfile, and more.

#### Customizing Language Mappings

You can customize language mappings by editing `.code-indexer/language-mappings.yaml`:

```yaml
# Add custom languages or modify existing mappings
python: [py, pyw, pyi]          # Multiple extensions
mylang: [ml, mli]               # Your custom language
javascript: [js, jsx]           # Modify existing mappings
```

Changes take effect on the next query execution. The file is automatically created during `cidx init` or on first use.

### Exclusion Filters

CIDX provides powerful exclusion filters to remove unwanted files from your search results. Exclusions always take precedence over inclusions.

#### Excluding Files by Language

```bash
# Exclude JavaScript files from results
cidx query "database implementation" --exclude-language javascript

# Exclude multiple languages
cidx query "api handlers" --exclude-language javascript --exclude-language typescript --exclude-language css

# Combine with language inclusion (Python only, no JS)
cidx query "web server" --language python --exclude-language javascript
```

#### Excluding Files by Path Pattern

```bash
# Exclude all test files
cidx query "production code" --exclude-path "*/tests/*" --exclude-path "*_test.py"

# Exclude dependency and cache directories
cidx query "application logic" \
  --exclude-path "*/node_modules/*" \
  --exclude-path "*/vendor/*" \
  --exclude-path "*/__pycache__/*"

# Exclude by file extension
cidx query "source code" --exclude-path "*.min.js" --exclude-path "*.pyc"

# Complex path patterns
cidx query "configuration" --exclude-path "*/build/*" --exclude-path "*/.*"  # Hidden files
```

#### Combining Multiple Filter Types

```bash
# Python files in src/, excluding tests and cache
cidx query "database models" \
  --language python \
  --path-filter "*/src/*" \
  --exclude-path "*/tests/*" \
  --exclude-path "*/__pycache__/*"

# High-relevance results, no test files or vendored code
cidx query "authentication logic" \
  --min-score 0.8 \
  --exclude-path "*/tests/*" \
  --exclude-path "*/vendor/*" \
  --exclude-language javascript
```

#### Common Exclusion Patterns

**Testing Files:**
```bash
--exclude-path "*/tests/*"        # Test directories
--exclude-path "*/test/*"         # Alternative test dirs
--exclude-path "*_test.py"        # Python test files
--exclude-path "*_test.go"        # Go test files
--exclude-path "*.test.js"        # JavaScript test files
--exclude-path "*/fixtures/*"     # Test fixtures
--exclude-path "*/mocks/*"        # Mock files
```

**Dependencies and Vendor Code:**
```bash
--exclude-path "*/node_modules/*"    # Node.js dependencies
--exclude-path "*/vendor/*"          # Vendor libraries
--exclude-path "*/.venv/*"           # Python virtual environments
--exclude-path "*/site-packages/*"   # Python packages
--exclude-path "*/bower_components/*" # Bower dependencies
```

**Build Artifacts and Cache:**
```bash
--exclude-path "*/build/*"        # Build output
--exclude-path "*/dist/*"         # Distribution files
--exclude-path "*/target/*"       # Maven/Cargo output
--exclude-path "*/__pycache__/*"  # Python cache
--exclude-path "*.pyc"            # Python compiled files
--exclude-path "*.pyo"            # Python optimized files
--exclude-path "*.class"          # Java compiled files
--exclude-path "*.o"              # Object files
--exclude-path "*.so"             # Shared libraries
```

**Generated and Minified Files:**
```bash
--exclude-path "*.min.js"         # Minified JavaScript
--exclude-path "*.min.css"        # Minified CSS
--exclude-path "*_pb2.py"         # Protocol buffer generated
--exclude-path "*.generated.*"    # Generated files
--exclude-path "*/migrations/*"   # Database migrations
```

### AI Platform Instructions

```bash
# Install Claude instructions in project root
cidx teach-ai --claude --project    # Creates ./CLAUDE.md

# Install Claude instructions globally
cidx teach-ai --claude --global     # Creates ~/.claude/CLAUDE.md

# Preview instruction content
cidx teach-ai --claude --show-only  # Show without writing

# Supported AI platforms
cidx teach-ai --claude              # Claude Code
cidx teach-ai --codex               # OpenAI Codex
cidx teach-ai --gemini              # Google Gemini
cidx teach-ai --opencode            # OpenCode
cidx teach-ai --q                   # Q
cidx teach-ai --junie               # Junie
```

**Template Location**: `prompts/ai_instructions/{platform}.md`

**Platform File Locations**:
| Platform | Project File | Global File |
|----------|-------------|-------------|
| Claude | `CLAUDE.md` | `~/.claude/CLAUDE.md` |
| Codex | `CODEX.md` | `~/.codex/instructions.md` |
| Gemini | `.gemini/styleguide.md` | N/A (project-only) |
| OpenCode | `AGENTS.md` | `~/.config/opencode/AGENTS.md` |
| Q | `.amazonq/rules/cidx.md` | `~/.aws/amazonq/Q.md` |
| Junie | `.junie/guidelines.md` | N/A (project-only) |

### Data Management Commands

```bash
# Quick cleanup (recommended)
cidx clean-data                 # Clear current project data
cidx clean-data --all-projects  # Clear all projects data

# Complete removal
cidx uninstall                  # Remove current project completely
cidx uninstall --confirm        # Skip confirmation prompt
cidx uninstall --wipe-all       # DANGEROUS: Complete system wipe

# Migration and maintenance
cidx clean-legacy               # Migrate from legacy containers
cidx optimize                   # Optimize vector database
cidx force-flush                # Force flush to disk (deprecated)
cidx force-flush --collection mycoll  # Flush specific collection
```

### Configuration Commands

```bash
# Configuration repair
cidx fix-config                 # Fix corrupted configuration
cidx fix-config --dry-run       # Preview fixes
cidx fix-config --verbose       # Detailed fix information
cidx fix-config --force         # Apply without confirmation

# Daemon configuration
cidx config --daemon            # Enable daemon mode
cidx config --no-daemon         # Disable daemon mode
```

### Global Options

```bash
# Available on most commands
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

## FTS-Specific Options

### Full-Text Search Configuration

```bash
# Case sensitivity
--case-sensitive      # Enable case-sensitive matching
--case-insensitive    # Force case-insensitive (default)

# Fuzzy matching
--fuzzy               # Enable fuzzy matching (edit distance 1)
--edit-distance N     # Set fuzzy tolerance (0-3, default: 0)
                      # 0=exact, 1=1 typo, 2=2 typos, 3=3 typos

# Context control
--snippet-lines N     # Lines of context around matches (0-50, default: 5)
                      # 0=list files only, no content snippets

# Regex mode
--regex               # Enable token-based regex (use with --fts)
```

### FTS Examples

```bash
# Find specific function names
cidx query "authenticate_user" --fts

# Case-sensitive class search
cidx query "UserAuthentication" --fts --case-sensitive

# Fuzzy search for typos
cidx query "respnse" --fts --fuzzy                    # Finds "response"
cidx query "athenticate" --fts --edit-distance 2      # Finds "authenticate"

# Minimal output (list files only)
cidx query "TODO" --fts --snippet-lines 0

# Extended context
cidx query "error" --fts --snippet-lines 10

# Filter by language and path
cidx query "test" --fts --language python --path-filter "*/tests/*"

# Hybrid search (both semantic and exact matching)
cidx query "login" --fts --semantic
```

### Regex Pattern Matching

Use `--regex` flag for token-based pattern matching (faster than grep on indexed repos):

```bash
# Find function definitions
cidx query "def" --fts --regex

# Find identifiers starting with "auth"
cidx query "auth.*" --fts --regex --language python

# Find test functions
cidx query "test_.*" --fts --regex --exclude-path "*/vendor/*"

# Find TODO comments (use lowercase for case-insensitive matching)
cidx query "todo" --fts --regex

# Case-sensitive regex (use uppercase for exact case match)
cidx query "ERROR" --fts --regex --case-sensitive
```

**Important Limitation - Token-Based Matching**: Tantivy regex operates on individual TOKENS, not full text:
- ✅ **Works**: `r"def"`, `r"login.*"`, `r"todo"`, `r"test_.*"`
- ❌ **Doesn't work**: `r"def\s+\w+"` (whitespace removed during tokenization)

**Case Sensitivity**: By default, regex searches are case-insensitive (patterns matched against lowercased content). Use `--case-sensitive` flag for exact case matching.

## Git History Search (Temporal Queries)

### Chunk Types

When querying git history with `--chunk-type`:

- **`commit_message`** - Search only commit messages
  - Returns: Commit descriptions, not code
  - Metadata: Hash, date, author, files changed count
  - Use for: Finding when features were added, bug fix history

- **`commit_diff`** - Search only code changes
  - Returns: Actual code diffs from commits
  - Metadata: File path, diff type (added/modified/deleted), language
  - Use for: Finding specific code changes, implementation history

- **(default)** - Search both messages and diffs
  - Returns: Mixed results ranked by semantic relevance
  - Use for: General historical code search

### Time Range Formats

```bash
# All history (1970 to 2100)
--time-range-all

# Specific date range
--time-range 2024-01-01..2024-12-31

# Recent timeframe
--time-range 2024-06-01..2024-12-31

# Single year
--time-range 2024-01-01..2024-12-31
```

### Temporal Search Use Cases

**1. Code Archaeology - When Was This Added?**
```bash
# Find when JWT authentication was introduced
cidx query "JWT token authentication" --time-range-all --quiet
```

**2. Bug History Research**
```bash
# Find all bug fixes related to database connections
cidx query "database connection bug" --time-range-all --chunk-type commit_message --quiet
```

**3. Author Code Analysis**
```bash
# Find all authentication-related work by specific developer
cidx query "authentication" --time-range-all --author "sarah@company.com" --quiet
```

**4. Feature Evolution Tracking**
```bash
# See how API endpoints changed over time
cidx query "API endpoint" --time-range 2023-01-01..2024-12-31 --language python --quiet
```

**5. Refactoring History**
```bash
# Find all refactoring work
cidx query "refactor" --time-range-all --chunk-type commit_message --limit 20 --quiet
```

## Vector Storage

Code Indexer uses FilesystemVectorStore for vector storage:

- **Container-free**: No Docker/Podman containers required
- **Instant startup**: No service initialization needed
- **Local storage**: Vectors stored as JSON files in `.code-indexer/index/`
- **Git-aware**: Uses blob hashes for clean files, content for dirty files

## Real-time Progress Display

During indexing, the progress display shows:
- File processing progress with counts and percentages
- Performance metrics: files/s, KB/s, active threads
- Individual file status with processing stages

Example progress: `15/100 files (15%) | 8.3 files/s | 156.7 KB/s | 12 threads`

Individual file status display:
```
├─ main.py (15.2 KB) starting
├─ utils.py (8.3 KB) chunking...
├─ config.py (4.1 KB) vectorizing...
├─ helpers.py (3.2 KB) finalizing...
├─ models.py (12.5 KB) complete ✓
```

## Configuration File

Configuration is stored in `.code-indexer/config.json`:
- `file_extensions`: File types to index
- `exclude_dirs`: Directories to skip
- `embedding_provider`: voyage-ai (determines chunk size automatically)
- `max_file_size`: Maximum file size in bytes (default: 1MB)
- `chunk_size`: Legacy setting (ignored, chunker uses model-aware sizing)
- `chunk_overlap`: Legacy setting (ignored, chunker uses 15% of chunk size)
- `voyage_ai.parallel_requests`: Thread count for VoyageAI (default: 8)

## Embedding Provider Token Counting

### VoyageAI Token Counting

**Token Counting Implementation**:
- Uses `embedded_voyage_tokenizer.py`, NOT voyageai library
- Critical for 120,000 token/batch API limit
- Lazy imports, caches per model (0.03ms)
- 100% identical to `voyageai.Client.count_tokens()`
- **DO NOT remove/replace** without extensive testing

**Batch Processing**:
- 120,000 token limit per batch enforced
- Automatic token-aware batching
- Transparent batch splitting


## Performance Notes

### Filter Performance

- Each exclusion filter adds minimal overhead (typically <2ms)
- Filters are applied during the search phase, not during indexing
- Use specific patterns when possible for better performance
- Complex glob patterns may have slightly higher overhead
- The order of filters does not affect performance

### FTS Performance

FTS queries use Tantivy index for efficient text search:
- **1.36x faster than grep** on indexed codebases (benchmark: 1.046s vs 1.426s avg)
- **Parallel execution** in hybrid mode (both searches run simultaneously)
- **Real-time index updates** in watch mode
- **Storage**: `.code-indexer/tantivy_index/`

## Related Documentation

- **[Architecture](architecture.md)** - System design and architecture decisions
- **[Algorithms](algorithms.md)** - Detailed algorithm descriptions
- **[Server Mode](server-mode.md)** - Multi-user server setup and API reference
- **[Development Guide](development.md)** - Contributor guidelines
