# SCIP Code Intelligence

✅ FACT-CHECKED (2025-12-31)

SCIP (Source Code Intelligence Protocol) provides precise code navigation, cross-references, and dependency analysis for CIDX. Unlike semantic search which finds similar code by meaning, SCIP provides exact symbol definitions, references, and relationships.

## Table of Contents

- [Quick Start](#quick-start)
- [Supported Languages](#supported-languages)
- [Available Commands](#available-commands)
- [Output Format](#output-format)
- [Query Parameters](#query-parameters)
- [Performance](#performance)
- [Use Cases](#use-cases)
- [Coverage Status](#coverage-status)
- [SCIP vs Semantic Search](#scip-vs-semantic-search)
- [Troubleshooting](#troubleshooting)

## Quick Start

Generate SCIP indexes for your codebase:

```bash
# Generate SCIP indexes
cidx scip generate

# Check generation status
cidx scip status
```

**Storage**: SCIP indexes are stored as SQLite databases in `.code-indexer/scip/*.scip.db`

**Note**: After generation completes, the original `.scip` protobuf files are automatically deleted. Only the `.scip.db` SQLite databases remain for queries.

## Supported Languages

SCIP indexing requires language-specific indexers:

- **Java** - `scip-java`
- **Kotlin** - `scip-java` (Kotlin support)
- **TypeScript** - `scip-typescript`
- **JavaScript** - `scip-typescript` (JavaScript support)
- **Python** - `scip-python`
- **C#** - `scip-dotnet`
- **Go** - `scip-go`

**Automatic Detection**: `cidx scip generate` automatically detects project languages and uses the appropriate indexers.

## Available Commands

### 1. Find Definition

Locate where a symbol is defined (class, function, method, variable):

```bash
# Find class definition
cidx scip definition "ClassName"

# Find method definition (exact match)
cidx scip definition "method_name" --exact

# Limit results
cidx scip definition "MyClass" --limit 5
```

**Use Cases**:
- Jump to symbol definition
- Locate source of imported symbols
- Understand symbol type (class vs function vs method)

### 2. Find References

Find all places where a symbol is used (imports, calls, instantiations):

```bash
# Find all usages of a class
cidx scip references "ClassName"

# Find all calls to a function (exact match)
cidx scip references "authenticate" --exact

# Find many references
cidx scip references "User" --limit 20
```

**Use Cases**:
- Find all code that depends on a symbol
- Identify all callsites before refactoring
- See usage examples of a symbol
- Understand symbol adoption across codebase

### 3. Find Dependencies

Show what a symbol directly depends on (imports, calls, uses):

```bash
# What does this class depend on?
cidx scip dependencies "MyClass"

# What does this function call?
cidx scip dependencies "process_data"
```

**Use Cases**:
- Understand symbol's requirements
- Identify external dependencies
- Plan refactoring by understanding coupling
- Trace data flow

### 4. Find Dependents

Show what directly depends on a symbol (reverse dependencies):

```bash
# What depends on this base class?
cidx scip dependents "BaseClass"

# What uses this utility function?
cidx scip dependents "core_function"
```

**Use Cases**:
- Assess refactoring impact
- Identify code that will break if symbol changes
- Understand symbol's reach in codebase
- Find potential testing scope

### 5. Impact Analysis

Multi-hop recursive analysis of change impact:

```bash
# Full impact analysis (default depth=3)
cidx scip impact "UserModel"

# Deeper analysis (up to depth=10)
cidx scip impact "authenticate" --depth 5
```

**What It Does**:
- Recursively finds all symbols affected by changing the target
- Returns complete dependency tree with depth tracking
- Provides file-level summaries of affected code

**Use Cases**:
- Comprehensive refactoring risk assessment
- Understanding cascading dependencies
- Generating test coverage scope
- Planning migration strategies

**Understanding Depth**:
- **Depth 1**: Direct dependents (files using the symbol directly)
- **Depth 2**: Dependents of dependents (second-order effects)
- **Depth 3**: Third-level dependents (ripple effects)

For most decisions, depth=3 captures meaningful impact. Deeper traversals rarely add actionable information.

### 6. Call Chain

Trace execution paths from one symbol to another:

```bash
# Find call chains from entry point to target
cidx scip callchain "login_user" "DatabaseManager"

# Trace specific path (deeper search)
cidx scip callchain "process_payment" "Logger" --max-depth 15
```

**What It Does**:
- Bidirectional BFS search for call paths
- Shows intermediate symbols in execution flow
- Identifies multiple paths if they exist

**Use Cases**:
- Trace request flow through system
- Understand how data reaches a function
- Debug execution paths
- Document code flow

### 7. Symbol Context

Get documentation and context for symbols:

```bash
# Get context for unfamiliar symbol
cidx scip context "DatabaseConnection"

# Find related symbols
cidx scip context "API" --limit 10
```

**What It Does**:
- Returns symbol documentation
- Shows related symbols and context
- Provides file location and metadata

**Use Cases**:
- Quick symbol lookup during code review
- Understanding unfamiliar code
- Finding related functionality
- Building mental model of codebase

## Output Format

All SCIP commands use **compact single-line output** for token efficiency:

```
module.path/ClassName#method() (src/module/file.py:42)
services/AuthService#authenticate() (src/services/auth.py:156)
models/User (src/models/user.py:12)
```

**Format**: `{module_path/SymbolName#method()} ({file_path}:{line})`

**Benefits**:
- **60-70% token reduction** vs verbose output
- **LLM-friendly**: Faster processing, lower costs
- **Human-readable**: Module-qualified names
- **Easy to parse**: Structured format for tools

**Example Comparison**:

Traditional verbose output:
```
Symbol: authenticate
  File: src/services/auth.py
  Line: 156
  Module: services.auth
  Type: method
  Class: AuthService
```

CIDX compact output:
```
services/AuthService#authenticate() (src/services/auth.py:156)
```

## Query Parameters

### Common Options (All Commands)

**--limit N**
- Maximum number of results to return
- Default: 0 (unlimited)
- Use low limits (5-10) for quick exploration
- Increase for comprehensive analysis

**--exact**
- Exact symbol name matching (no substring matching)
- Default: false (fuzzy substring matching)
- Use when you know exact symbol name
- Prevents false positives

**Examples**:
```bash
# Fuzzy matching (default) - "User" matches "UserService", "UserManager"
cidx scip definition "User"

# Exact matching - only "UserService"
cidx scip definition "UserService" --exact
```

### Impact Analysis Options

**--depth N**
- Maximum traversal depth for recursive analysis
- Default: 3
- Range: 1-10
- Higher depth = more complete analysis but slower

**Example**:
```bash
# Deep impact analysis
cidx scip impact "CoreClass" --depth 5
```

### Call Chain Options

**--max-depth N**
- Maximum chain length to search
- Default: 10
- Range: 1-20
- Higher depth finds longer call chains

**Example**:
```bash
# Find deep call chains
cidx scip callchain "entrypoint" "target" --max-depth 15
```

## Performance

SCIP queries use **DatabaseBackend with SQL Recursive CTEs** for optimal performance:

| Command | Performance | Notes |
|---------|-------------|-------|
| **Definition** | <0.5s | FTS5-optimized symbol lookup |
| **References** | <1s | Indexed symbol lookups |
| **Dependencies** | <1s @ depth=1 | SQL CTE optimization |
| **Dependents** | <1s @ depth=1 | SQL CTE optimization |
| **Call Chain** | <5s @ depth=10 | Bidirectional BFS with SQL CTEs |
| **Impact Analysis** | <2s @ depth=3 | Multi-hop graph traversal |
| **Context** | <2s | Symbol documentation lookup |

### Architecture Optimizations

1. **SQL Recursive CTEs**: Replace Python recursion with database-level traversal (O(1) query complexity)
2. **FTS5 Indexes**: Full-text search indexes for fast symbol name lookups
3. **Bidirectional BFS**: Efficient call chain tracing from both ends
4. **Database Indexes**: Optimized indexes on `call_graph` and `symbol_references` tables

### Query Limits

To ensure consistent <2s response times:

| Limit | Value | Description |
|-------|-------|-------------|
| **Max Depth** | 10 | Transitive queries follow at most 10 hops |
| **Max Call Chain Depth** | 10 | Call chain default depth |

**Why These Limits?**

- **Depth=10**: Maximum depth cap prevents exponential explosion
- **Depth=3 default**: Captures meaningful impact for most refactoring decisions
- **Sub-2s queries**: Ensures responsive interactive experience

**Note**: The codebase uses MAX_TRAVERSAL_DEPTH = 10 and MAX_CALL_CHAIN_DEPTH = 10 as hard limits.

### Storage Efficiency

- **SQLite database**: 30-50% smaller than raw `.scip` files
- **Automatic cleanup**: Original `.scip` files deleted after database generation
- **Indexed lookups**: Fast queries without loading entire index

## Use Cases

### Code Navigation

**Scenario**: Find where a class is defined and how it's used

```bash
# Find definition
cidx scip definition "UserService"

# Find all usages
cidx scip references "UserService"
```

### Refactoring Analysis

**Scenario**: Planning to refactor a legacy class

```bash
# See what will break
cidx scip dependents "LegacyAuth"

# Comprehensive impact
cidx scip impact "LegacyAuth" --depth 3
```

### Architecture Understanding

**Scenario**: Understanding system dependencies

```bash
# What does the payment service depend on?
cidx scip dependencies "PaymentService"

# How does payment flow through the system?
cidx scip callchain "handle_payment_request" "PaymentService"
```

### Code Review

**Scenario**: Reviewing unfamiliar code

```bash
# Get context for symbol
cidx scip context "ConfigManager"

# Verify deprecated function isn't used
cidx scip references "deprecated_function"
```

### Bug Investigation

**Scenario**: Tracing how data flows to a bug location

```bash
# Find call chains to buggy function
cidx scip callchain "buggy_function" "entry_point"

# See what depends on the fix
cidx scip dependents "fixed_function"
```

## Coverage Status

SCIP is available across all CIDX interfaces:

| Interface | Coverage | Commands Available |
|-----------|----------|-------------------|
| **CLI** | 9/9 (100%) | All commands (generate, status, definition, references, dependencies, dependents, impact, callchain, context) |
| **REST API** | 7/7 (100%) | All query commands (definition, references, dependencies, dependents, impact, callchain, context) |
| **MCP Tools** | 7/7 (100%) | All query commands (definition, references, dependencies, dependents, impact, callchain, context) |
| **Web UI** | 4/7 (57%) | definition, references, dependencies, dependents |

**Missing from Web UI**: impact, callchain, context (use CLI/API/MCP instead)

## SCIP vs Semantic Search

Understanding when to use each approach:

| Feature | SCIP | Semantic Search |
|---------|------|-----------------|
| **Precision** | Exact symbol matches | Similar code by meaning |
| **Speed** | <200ms typical | ~20ms (HNSW) |
| **Use Case** | Navigate existing code | Discover relevant code |
| **Language Support** | Requires SCIP indexer | Any text-based language |
| **Relationships** | Explicit (imports, calls) | Implicit (similarity) |
| **Cross-repo** | Yes (with SCIP indexes) | Yes (with semantic indexes) |
| **Symbol Types** | Classes, methods, functions | Code chunks, concepts |
| **Accuracy** | 100% (compiler-based) | ~85-95% (ML-based) |

### When to Use SCIP

- You know the symbol name or can guess it
- You need exact locations (definition, references)
- You want to understand dependencies
- You're refactoring and need impact analysis
- You need call chain tracing

### When to Use Semantic Search

- You don't know the symbol name
- You're searching by concept ("authentication logic")
- You want to find similar implementations
- You're exploring unfamiliar code
- Language doesn't have SCIP indexer

### Using Both Together

Best results often come from combining approaches:

1. **Semantic search** to discover relevant code areas
2. **SCIP** to navigate precise relationships within those areas

Example workflow:
```bash
# 1. Find authentication-related code (semantic)
cidx query "JWT authentication" --limit 10

# 2. Navigate to specific implementations (SCIP)
cidx scip definition "JWTAuthenticator"
cidx scip dependencies "JWTAuthenticator"
```

## Troubleshooting

### SCIP Indexes Not Found

**Symptom**: Commands return "No SCIP indexes found"

**Solution**:
```bash
# Check status
cidx scip status

# Generate indexes if missing
cidx scip generate
```

### Language Not Supported

**Symptom**: "No SCIP indexer available for language X"

**Cause**: Language doesn't have a SCIP indexer yet

**Supported**: Java, Kotlin, TypeScript, JavaScript, Python, C#, Go

**Workaround**: Use semantic search or FTS for unsupported languages

### Slow Query Performance

**Symptom**: Queries take >2 seconds

**Possible Causes**:
1. Very deep traversal (`--depth` too high)
2. Large codebase (>100K symbols)
3. Database not optimized

**Solutions**:
```bash
# Reduce depth
cidx scip impact "Symbol" --depth 2

# Use limits
cidx scip references "Symbol" --limit 20

# Regenerate indexes
cidx scip generate
```

### No Results Found

**Symptom**: Query returns 0 results for known symbol

**Possible Causes**:
1. Exact matching too strict
2. Symbol name mismatch
3. Symbol not indexed

**Solutions**:
```bash
# Try fuzzy matching (remove --exact)
cidx scip definition "User"

# Try substring
cidx scip definition "Service"

# Regenerate indexes
cidx scip generate
```

### .scip Files Missing

**Symptom**: Looking for `.scip` files but can't find them

**This is normal**: After database generation, original `.scip` files are automatically deleted. Only `.scip.db` SQLite databases remain. Queries work with the `.scip.db` files.

**Verification**:
```bash
# Check for database files
ls -lh .code-indexer/scip/*.scip.db

# Should see files like: index.scip.db
```

### Call Chain Not Found

**Symptom**: No chains found between known symbols

**Possible Causes**:
1. Symbols not directly connected
2. Chain longer than `--max-depth`
3. Connection through unsupported language boundary

**Solutions**:
```bash
# Increase depth
cidx scip callchain "from" "to" --max-depth 15

# Check if symbols exist
cidx scip definition "from"
cidx scip definition "to"

# Try intermediate steps manually
cidx scip dependencies "from"
cidx scip dependents "to"
```

### High Memory Usage

**Symptom**: `cidx scip generate` uses excessive memory

**Cause**: Large projects generate large SCIP indexes

**Solutions**:
- Generate per-language: Run indexers individually
- Increase available memory
- Exclude test directories if not needed

---

## Next Steps

- **Return to main documentation**: [README](../../README.md)
- **Learn query capabilities**: [Query Guide](../query-guide.md)
- **Explore semantic search**: [README - Semantic Search](../../README.md#semantic-search-default)
- **Understand architecture**: [Architecture](../architecture.md)

---

