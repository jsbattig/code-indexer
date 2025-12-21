# Full-Text Search (FTS) - Exact Matching and Patterns

Full-text search finds exact text matches and patterns in code. Use this for identifiers, function names, TODO comments, and typo debugging.

## Decision Rule

**Use FTS when you need**:
- Exact names and identifiers: `UserService`, `authenticate_user`
- TODO/FIXME comments: Find all TODOs
- Specific string literals: Configuration keys, error messages
- Typo debugging: Find misspelled identifiers
- Token-based patterns: `test_.*`, `def.*auth`

**Do NOT use FTS when you need**:
- Semantic understanding: "What code does X" → Use semantic search
- Broad concept search: "authentication logic" → Use semantic search

## Basic FTS Usage

```bash
# Find exact class name
cidx query "UserService" --fts --quiet

# Find function name
cidx query "authenticate_user" --fts --quiet

# Find TODO comments
cidx query "TODO" --fts --case-sensitive --quiet
```

## Core FTS Flags

### Enable FTS
- `--fts` - Enable full-text search mode
  - REQUIRED for all FTS operations
  - Example: `cidx query "UserService" --fts --quiet`

### Case Sensitivity
- `--case-sensitive` - Exact case matching
  - Default: case-insensitive
  - Useful for TODO comments, constants, acronyms
  - Example: `cidx query "TODO" --fts --case-sensitive --quiet`

### Fuzzy Matching
- `--fuzzy` - Enable fuzzy matching for typos
  - Finds similar matches (handles misspellings)
  - Example: `cidx query "athenticate" --fts --fuzzy --quiet`

- `--edit-distance N` - Maximum edit distance for fuzzy matching
  - Default: 2
  - Higher = more lenient matching
  - Example: `cidx query "usrService" --fts --fuzzy --edit-distance 3 --quiet`

### Snippet Control
- `--snippet-lines N` - Lines of context around match
  - Default: 2
  - Example: `cidx query "authenticate" --fts --snippet-lines 5 --quiet`

## Regex Mode - Pattern Matching

**10-50x faster than grep** for token-based pattern matching.

### Enable Regex
```bash
# Basic regex search
cidx query "def.*auth" --fts --regex --quiet

# Find test functions
cidx query "test_.*" --fts --regex --quiet

# Find private methods (Python)
cidx query "_.*_init" --fts --regex --quiet
```

### Regex Flags
- `--fts --regex` - Enable token-based regex matching
  - INCOMPATIBLE with `--semantic` and `--fuzzy`
  - Uses ripgrep-style token matching
  - Example: `cidx query "class.*User" --fts --regex --quiet`

### Token-Based Matching Explained

**How it works**: Regex matches against individual tokens (words), not full text with whitespace.

**What works** (token boundaries):
```bash
# Function definitions
cidx query "def" --fts --regex --quiet

# Login-related functions
cidx query "login.*" --fts --regex --quiet

# Test functions
cidx query "test_.*" --fts --regex --quiet

# Class definitions
cidx query "class.*Service" --fts --regex --quiet
```

**What doesn't work** (whitespace matching):
```bash
# ❌ This won't work (whitespace removed in tokenization)
cidx query "def\s+\w+" --fts --regex --quiet

# ✅ Use this instead
cidx query "def" --fts --regex --quiet
```

### Practical Regex Examples

```bash
# Find all function definitions
cidx query "def" --fts --regex --language python --quiet

# Find all class definitions with "Service" in name
cidx query "class.*Service" --fts --regex --language python --quiet

# Find test functions matching pattern
cidx query "test_.*auth" --fts --regex --language python --quiet

# Find private methods
cidx query "_.*" --fts --regex --language python --quiet

# Find async functions
cidx query "async.*def" --fts --regex --language python --quiet
```

## Hybrid Mode - FTS + Semantic

Combines exact matching with semantic understanding.

```bash
# Run both FTS and semantic in parallel
cidx query "UserService" --fts --semantic --quiet

# Useful when you want both:
# 1. Exact name matches (FTS)
# 2. Conceptually similar code (semantic)
```

**Use cases**:
- Finding all references to a class AND similar patterns
- Locating exact identifiers AND related functionality
- Comprehensive search when unsure if exact match exists

## Language Filtering with FTS

All semantic search filters work with FTS:

```bash
# FTS in Python only
cidx query "authenticate" --fts --language python --quiet

# Exclude test files
cidx query "UserService" --fts --exclude-path "*/tests/*" --quiet

# Specific directory
cidx query "TODO" --fts --path-filter "src/auth/*" --quiet

# Specific file extensions
cidx query "FIXME" --fts --file-extensions py,js --quiet
```

## Practical Examples

### Finding Function Definitions

```bash
# Find specific function by exact name
cidx query "authenticate_user" --fts --case-sensitive --quiet

# Find all functions with "auth" in name
cidx query "auth" --fts --quiet

# Find all async functions
cidx query "async" --fts --language typescript --quiet
```

### Finding Class Definitions

```bash
# Exact class name
cidx query "UserService" --fts --case-sensitive --quiet

# All classes ending in "Service"
cidx query "Service" --fts --quiet

# Pattern-based search for service classes
cidx query ".*Service" --fts --regex --quiet
```

### Finding TODO/FIXME Comments

```bash
# All TODO comments
cidx query "TODO" --fts --case-sensitive --quiet

# All FIXME comments with context
cidx query "FIXME" --fts --case-sensitive --snippet-lines 5 --quiet

# TODOs in specific directory
cidx query "TODO" --fts --case-sensitive --path-filter "src/backend/*" --quiet

# All code comments markers
cidx query "TODO|FIXME|HACK|XXX" --fts --regex --case-sensitive --quiet
```

### Finding Configuration Keys

```bash
# Specific config key
cidx query "DATABASE_URL" --fts --case-sensitive --quiet

# All environment variables (uppercase pattern)
cidx query "[A-Z_]+" --fts --regex --quiet

# Config keys in specific file
cidx query "API_KEY" --fts --path-filter "*/config/*" --quiet
```

### Finding String Literals

```bash
# Specific error message
cidx query "Authentication failed" --fts --quiet

# Log statements
cidx query "logger.error" --fts --quiet

# HTTP status codes
cidx query "404" --fts --quiet
```

### Typo Debugging

```bash
# Find misspelled "authenticate" (fuzzy matching)
cidx query "athenticate" --fts --fuzzy --quiet

# Broader edit distance for severe typos
cidx query "usrService" --fts --fuzzy --edit-distance 3 --quiet

# Case-insensitive fuzzy search
cidx query "userervice" --fts --fuzzy --quiet
```

### Pattern-Based Code Search

```bash
# All test functions
cidx query "test_.*" --fts --regex --language python --quiet

# All private Python methods
cidx query "_.*" --fts --regex --language python --quiet

# All getter methods (Java/TypeScript)
cidx query "get[A-Z].*" --fts --regex --quiet

# All constant definitions (uppercase)
cidx query "[A-Z_]{2,}" --fts --regex --quiet
```

## Combining FTS with Other Filters

```bash
# Case-sensitive search in Python backend only
cidx query "UserService" \
  --fts \
  --case-sensitive \
  --language python \
  --path-filter "backend/*" \
  --quiet

# Fuzzy search excluding tests with context
cidx query "athenticate" \
  --fts \
  --fuzzy \
  --edit-distance 2 \
  --exclude-path "*/tests/*" \
  --snippet-lines 5 \
  --quiet

# Regex search for test functions with limit
cidx query "test_.*auth" \
  --fts \
  --regex \
  --language python \
  --limit 10 \
  --quiet
```

## Performance Comparison

**FTS + Regex vs Grep**:
- **10-50x faster** than traditional grep for token patterns
- Indexed search (faster than filesystem scanning)
- Parallel query execution
- Optimized for code structure

**When FTS is faster than semantic**:
- Exact identifier matching (no embedding computation)
- Simple pattern matching
- Large codebases (no similarity scoring)

**When semantic is better**:
- Conceptual search ("authentication logic")
- Understanding functionality
- Finding similar code patterns

## Troubleshooting

### No Results Found

**Check case sensitivity**:
```bash
# Try case-insensitive first
cidx query "userservice" --fts --quiet

# Then try exact case
cidx query "UserService" --fts --case-sensitive --quiet
```

**Try fuzzy matching**:
```bash
# Handle typos
cidx query "usrService" --fts --fuzzy --quiet
```

**Remove filters**:
```bash
# Remove language/path filters to broaden search
cidx query "UserService" --fts --quiet
```

### Too Many Results

**Add language filter**:
```bash
cidx query "test" --fts --language python --quiet
```

**Add path filter**:
```bash
cidx query "config" --fts --path-filter "src/backend/*" --quiet
```

**Use case-sensitive**:
```bash
cidx query "UserService" --fts --case-sensitive --quiet
```

**Use exact matching** (disable fuzzy):
```bash
# Fuzzy disabled by default, ensure you're not using --fuzzy
cidx query "UserService" --fts --quiet
```

### Regex Pattern Not Working

**Remember token-based matching**:
```bash
# ❌ Won't work (whitespace)
cidx query "def\s+authenticate" --fts --regex --quiet

# ✅ Works (token boundary)
cidx query "def.*authenticate" --fts --regex --quiet
```

**Test pattern incrementally**:
```bash
# Start simple
cidx query "test" --fts --regex --quiet

# Add complexity
cidx query "test_.*" --fts --regex --quiet

# Add specificity
cidx query "test_.*auth" --fts --regex --quiet
```

### Performance Issues

**Use language filter** to reduce search space:
```bash
cidx query "TODO" --fts --language python --quiet
```

**Limit results**:
```bash
cidx query "test" --fts --limit 10 --quiet
```

**Use path filter** to narrow scope:
```bash
cidx query "config" --fts --path-filter "src/*" --quiet
```

## When to Use FTS vs Semantic

| Need | Use FTS | Use Semantic |
|------|---------|--------------|
| Exact function name | ✅ `--fts` | ❌ |
| Understanding behavior | ❌ | ✅ semantic |
| TODO comments | ✅ `--fts --case-sensitive` | ❌ |
| Pattern matching | ✅ `--fts --regex` | ❌ |
| Code concepts | ❌ | ✅ semantic |
| Typo debugging | ✅ `--fts --fuzzy` | ❌ |
| "What does X do" | ❌ | ✅ semantic |
| Configuration keys | ✅ `--fts` | ❌ |
