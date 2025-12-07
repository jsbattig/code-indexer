# CIDX MCP Bridge Query Guide

Last Updated: 2025-11-26

## Overview

This guide demonstrates practical query patterns using the CIDX MCP Bridge search_code tool. All examples use verified parameters from src/code_indexer/server/mcp/tools.py:9-147.

## Query Decision Matrix

Choose search mode based on your use case:

| Use Case | Search Mode | Key Parameters | Example |
|----------|-------------|----------------|---------|
| Find code by meaning | semantic | min_score, accuracy | "authentication logic" |
| Find exact function names | fts | case_sensitive | "authenticate_user" |
| Find code patterns | fts + regex | regex, case_sensitive | "test_.*auth" |
| Find recent changes | semantic + temporal | time_range, author | "bug fix" in last month |
| Find with typo tolerance | fts + fuzzy | fuzzy, edit_distance | "authentcation" (typo) |
| Best of both worlds | hybrid | min_score, fuzzy | "login handling" |

## Semantic Search Basics

Semantic search finds code by meaning, not exact text matching. Uses VoyageAI embeddings for vector similarity.

### Basic Semantic Query

Find authentication-related code:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "user authentication",
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

Default behavior:
- search_mode: "semantic" (default)
- min_score: 0.5 (default)
- accuracy: "balanced" (default)
- limit: 5 (conserve context tokens)

### Adjust Relevance Threshold

Filter out low-relevance results:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database connection pooling",
      "min_score": 0.8,
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

min_score recommendations:
- 0.5-0.6: Broad search, more results
- 0.7-0.8: Focused search, higher relevance
- 0.9+: Very strict, only near-exact semantic matches

### High-Accuracy Search

Prioritize precision over speed:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "error handling strategy",
      "accuracy": "high",
      "min_score": 0.75,
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

accuracy options:
- "fast": Lower accuracy, faster response
- "balanced": Default, good tradeoff
- "high": Higher accuracy, slower response

## Full-Text Search (FTS)

FTS finds exact token matches. Ideal for function names, class names, identifiers.

### Basic FTS Query

Find exact function name:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authenticate_user",
      "search_mode": "fts",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Case-Sensitive FTS

Distinguish between "User" and "user":

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "User",
      "search_mode": "fts",
      "case_sensitive": true,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Adjust Context Lines

Show more code around matches:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "validate_token",
      "search_mode": "fts",
      "snippet_lines": 15,
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

snippet_lines options:
- 0: List matching files only, no context
- 1-5: Minimal context
- 5-10: Standard context (default: 5)
- 10-20: More context for understanding
- 20-50: Maximum context (large responses)

## Regex Pattern Matching

Regex mode enables token-based pattern matching. 10-50x faster than grep.

### Find Test Functions

Pattern: Functions starting with "test_":

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test_.*",
      "search_mode": "fts",
      "regex": true,
      "limit": 20
    }
  },
  "id": 1
}' | cidx-bridge
```

### Find Auth-Related Functions

Pattern: Functions containing "auth":

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": ".*auth.*",
      "search_mode": "fts",
      "regex": true,
      "case_sensitive": false,
      "limit": 15
    }
  },
  "id": 1
}' | cidx-bridge
```

### Find Function Definitions

Pattern: Python function definitions:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "def.*",
      "search_mode": "fts",
      "regex": true,
      "language": "python",
      "limit": 30
    }
  },
  "id": 1
}' | cidx-bridge
```

Token-based regex limitations:
- Works: `def`, `login.*`, `test_.*`
- Doesn't work: `def\s+\w+` (whitespace removed during indexing)

## Fuzzy Matching (Typo Tolerance)

Fuzzy matching handles typos and spelling variations.

### Basic Fuzzy Search

Find "authentication" even if typed as "authentcation":

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentcation",
      "search_mode": "fts",
      "fuzzy": true,
      "edit_distance": 1,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Higher Typo Tolerance

Allow 2 typos:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "databse conection",
      "search_mode": "fts",
      "fuzzy": true,
      "edit_distance": 2,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

edit_distance recommendations:
- 0: Exact match only (no fuzzy)
- 1: 1 typo allowed (recommended for most cases)
- 2: 2 typos allowed (broader matches, less precise)
- 3: 3 typos allowed (very broad, may have false positives)

Incompatibility: fuzzy and regex are mutually exclusive.

## Filtering

### Language Filtering

Search only Python files:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database query",
      "language": "python",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

Supported languages (from src/code_indexer/server/mcp/tools.py:45):
c, cpp, csharp, dart, go, java, javascript, kotlin, php, python, ruby, rust, scala, swift, typescript, css, html, vue, markdown, xml, json, yaml, bash, shell

Language aliases work: "python" = "py", "javascript" = "js", "typescript" = "ts"

### Exclude Language

Search all files except JavaScript:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "configuration",
      "exclude_language": "javascript",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Path Filtering

Search only in test files:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "mock data",
      "path_filter": "*/tests/*",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

Glob pattern examples:
- `*/tests/*`: Files in any tests directory
- `*/src/**/*.py`: Python files anywhere under src
- `**/models/*.py`: Python files in any models directory
- `*.test.js`: Test files at any level

### Exclude Path

Exclude test files and vendor code:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "API endpoint",
      "exclude_path": "*/tests/*",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

Multiple exclusions (not supported directly, use broader patterns):

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "API endpoint",
      "exclude_path": "**/vendor/**",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### File Extension Filtering

Search only Markdown and RST files:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "installation instructions",
      "file_extensions": [".md", ".rst"],
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Combined Filtering

Python files in src directory, exclude tests:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "error handling",
      "language": "python",
      "path_filter": "*/src/**/*.py",
      "exclude_path": "*/tests/*",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

## Temporal Search (Git History)

Temporal search requires temporal index built with `cidx index --index-commits`.

### Search Recent Changes

Find code added/modified in 2024:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "JWT authentication",
      "time_range": "2024-01-01..2024-12-31",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Search All Git History

Find when feature was added:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "OAuth integration",
      "time_range_all": true,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Code at Specific Commit

Find code as it existed at specific commit:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database schema",
      "at_commit": "abc123ef",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

Commit references:
- Commit hash: `abc123ef`
- Relative: `HEAD~5`, `HEAD~10`
- Tag: `v1.0.0`

### Include Removed Files

Find deleted authentication code:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "legacy auth",
      "time_range_all": true,
      "include_removed": true,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

Response includes `is_removed` flag in `temporal_context`.

### Code Evolution Timeline

Track how code changed over time:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentication flow",
      "time_range_all": true,
      "show_evolution": true,
      "evolution_limit": 15,
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

Response includes commit history with diffs. Warning: Increases response size significantly.

evolution_limit recommendations:
- 5-10: Recent changes only
- 10-20: Medium history
- 20+: Complete history (very large responses)

### Filter by Author

Find changes by specific developer:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "refactoring",
      "time_range": "2024-01-01..2024-12-31",
      "author": "developer@example.com",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

Author can be name or email.

### Search Commit Messages

Find commits by message content:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "bug fix",
      "time_range_all": true,
      "chunk_type": "commit_message",
      "limit": 20
    }
  },
  "id": 1
}' | cidx-bridge
```

chunk_type options:
- "commit_message": Search commit messages
- "commit_diff": Search code diffs (default)

### Filter by Diff Type

Find only newly added code:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "error handling",
      "time_range": "2024-06-01..2024-12-31",
      "diff_type": "added",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

diff_type options:
- "added": New code
- "modified": Changed code
- "deleted": Removed code
- "renamed": Renamed files
- "binary": Binary file changes

Multiple types: `"added,modified"`

## Hybrid Search

Hybrid mode combines semantic and FTS for best results.

### Basic Hybrid Search

Get both semantic and exact matches:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "login validation",
      "search_mode": "hybrid",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Hybrid with Fuzzy

Semantic search with typo tolerance:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentcation handlr",
      "search_mode": "hybrid",
      "fuzzy": true,
      "edit_distance": 2,
      "min_score": 0.7,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Hybrid with Filtering

Best of both worlds with language filter:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database migration",
      "search_mode": "hybrid",
      "language": "python",
      "min_score": 0.75,
      "snippet_lines": 10,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

## Performance Tips

### Start with Small Limits

Context token conservation:

```bash
# Initial exploration - limit=5
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "API implementation",
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge

# If insufficient, increase to limit=10
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "API implementation",
      "limit": 10
    }
  },
  "id": 2
}' | cidx-bridge
```

Limit recommendations:
- limit=5: Initial exploration, conserve tokens
- limit=10: Standard queries (default)
- limit=20-30: Comprehensive searches
- limit=50+: Exhaustive searches (high token consumption)

### Use Specific Filters

Narrow search scope for faster results:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "configuration",
      "language": "python",
      "path_filter": "*/src/config/*",
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

Filtering reduces search space:
- Language filter: Scans fewer files
- Path filter: Limits directory scope
- Exclude path: Skips irrelevant code

### Choose Appropriate Accuracy

Balance speed vs precision:

```bash
# Fast exploration
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "helper functions",
      "accuracy": "fast",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge

# Precise final search
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "critical security logic",
      "accuracy": "high",
      "min_score": 0.85,
      "limit": 5
    }
  },
  "id": 2
}' | cidx-bridge
```

### Minimize Context Lines

Reduce response size for large result sets:

```bash
# List only (no context)
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "TODO",
      "search_mode": "fts",
      "snippet_lines": 0,
      "limit": 50
    }
  },
  "id": 1
}' | cidx-bridge

# Minimal context
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "FIXME",
      "search_mode": "fts",
      "snippet_lines": 2,
      "limit": 30
    }
  },
  "id": 2
}' | cidx-bridge
```

### Use FTS for Exact Searches

FTS faster than semantic for exact matches:

```bash
# Fast exact search
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "UserAuthenticationService",
      "search_mode": "fts",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

## Practical Examples

### Find All TODOs

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "TODO",
      "search_mode": "fts",
      "case_sensitive": true,
      "snippet_lines": 3,
      "limit": 50
    }
  },
  "id": 1
}' | cidx-bridge
```

### Find Security-Critical Code

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "password hashing encryption",
      "search_mode": "semantic",
      "accuracy": "high",
      "min_score": 0.8,
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Find Recent Bug Fixes

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "bug fix",
      "time_range": "2024-10-01..2024-11-26",
      "chunk_type": "commit_message",
      "limit": 20
    }
  },
  "id": 1
}' | cidx-bridge
```

### Find API Endpoint Implementations

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "REST API endpoint",
      "language": "python",
      "path_filter": "*/api/*",
      "exclude_path": "*/tests/*",
      "limit": 15
    }
  },
  "id": 1
}' | cidx-bridge
```

### Find Configuration Files

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "environment configuration",
      "file_extensions": [".yaml", ".yml", ".json", ".env"],
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

### Track Feature Implementation

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "OAuth2 implementation",
      "time_range_all": true,
      "show_evolution": true,
      "evolution_limit": 10,
      "author": "lead-dev@example.com",
      "limit": 5
    }
  },
  "id": 1
}' | cidx-bridge
```

## Common Patterns

### Code Review Workflow

1. Find recent changes by developer:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": ".*",
      "time_range": "2024-11-20..2024-11-26",
      "author": "developer@example.com",
      "diff_type": "added,modified",
      "limit": 30
    }
  },
  "id": 1
}' | cidx-bridge
```

2. Review security implications:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentication authorization security",
      "time_range": "2024-11-20..2024-11-26",
      "limit": 10
    }
  },
  "id": 2
}' | cidx-bridge
```

### Bug Investigation

1. Find error-prone code:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "null pointer exception error",
      "search_mode": "semantic",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

2. Check recent bug fixes:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "fix.*null",
      "search_mode": "fts",
      "regex": true,
      "time_range": "2024-10-01..2024-11-26",
      "chunk_type": "commit_message",
      "limit": 15
    }
  },
  "id": 2
}' | cidx-bridge
```

### Documentation Search

Find README and setup instructions:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "installation setup configuration",
      "file_extensions": [".md", ".rst", ".txt"],
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

## Multi-Repository Search (Omni-Search)

Omni-search enables querying across multiple repositories simultaneously using a single MCP tool call. Available in search_code, list_files, regex_search, git_log, and git_search_commits tools.

### Feature Overview

The repository_alias parameter accepts either a single string or an array of repository aliases, enabling multi-repository queries:

```bash
# Single repository (standard)
"repository_alias": "backend-global"

# Multiple repositories (omni-search)
"repository_alias": ["evolution-global", "evo-mobile-global", "backend-global"]
```

When multiple repositories are specified, CIDX performs parallel searches across all specified repositories and aggregates results according to the aggregation_mode parameter.

### Aggregation Modes

CIDX provides two aggregation strategies for combining results from multiple repositories:

#### Global Aggregation (Default)

Sorts ALL results by score across all repositories and returns the top N matches, regardless of source repository.

**Best for**: Finding the absolute best matches when you want the highest quality results across your entire codebase.

**Characteristics**:
- Results sorted by score globally (highest scores first)
- May return all results from one repository if it has the best matches
- Guarantees the top N results by quality
- Default behavior when aggregation_mode not specified

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authentication flow",
      "repository_alias": ["evolution-global", "evo-mobile-global", "backend-global"],
      "search_mode": "semantic",
      "aggregation_mode": "global",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

#### Per-Repository Aggregation

Takes proportional results from each repository (limit / number_of_repos from each), ensuring representation from every repository.

**Best for**: Getting a balanced view across multiple codebases when you need results from each repository.

**Characteristics**:
- Results distributed proportionally across repositories
- Each repository contributes limit/N results (rounded)
- Guarantees representation from every specified repository
- Results still sorted by score within each repository's contribution

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "login validation",
      "repository_alias": ["frontend-global", "backend-global"],
      "search_mode": "semantic",
      "aggregation_mode": "per_repo",
      "limit": 10
    }
  },
  "id": 1
}' | cidx-bridge
```

With `aggregation_mode: "per_repo"` and 2 repositories:
- Each repository contributes 5 results (10/2)
- Total results: 10 (balanced across both repositories)
- Even if frontend has better scores, backend still contributes 5 results

### Practical Examples

#### Cross-Repository Semantic Search

Find authentication code across three microservices:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "JWT token validation",
      "repository_alias": ["evolution-global", "evo-mobile-global", "backend-global"],
      "search_mode": "semantic",
      "aggregation_mode": "global",
      "accuracy": "high",
      "min_score": 0.75,
      "limit": 15
    }
  },
  "id": 1
}' | cidx-bridge
```

#### Balanced Search Across Frontend and Backend

Get results from both repositories equally:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "error handling",
      "repository_alias": ["frontend-global", "backend-global"],
      "aggregation_mode": "per_repo",
      "language": "typescript",
      "limit": 20
    }
  },
  "id": 1
}' | cidx-bridge
```

Result: 10 results from frontend-global, 10 from backend-global.

#### Cross-Repository FTS Search

Find specific function names across all services:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "authenticateUser",
      "repository_alias": ["auth-service-global", "api-gateway-global", "user-service-global"],
      "search_mode": "fts",
      "case_sensitive": true,
      "limit": 30
    }
  },
  "id": 1
}' | cidx-bridge
```

#### Cross-Repository Regex Pattern Search

Find test functions across multiple test suites:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test_.*integration",
      "repository_alias": ["backend-global", "api-global", "worker-global"],
      "search_mode": "fts",
      "regex": true,
      "aggregation_mode": "per_repo",
      "limit": 30
    }
  },
  "id": 1
}' | cidx-bridge
```

Result: 10 results from each repository (balanced representation).

#### Multi-Repository Temporal Search

Find when authentication was added across all services:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "OAuth2 integration",
      "repository_alias": ["auth-service-global", "frontend-global", "backend-global"],
      "time_range_all": true,
      "chunk_type": "commit_message",
      "aggregation_mode": "global",
      "limit": 20
    }
  },
  "id": 1
}' | cidx-bridge
```

### Performance Expectations

Based on benchmark testing with semantic search (high accuracy):

| Repositories | Avg Latency | Performance Characteristics |
|--------------|-------------|----------------------------|
| 1 repo | ~900ms | Baseline single-repository search |
| 3 repos | ~1300ms | 400ms overhead for 2 additional repos |
| 5 repos | ~1900ms | Linear scaling (~400ms per repo) |

**Key Performance Insights**:
- Linear scaling: ~400ms per additional repository
- Parallel execution: Repositories searched concurrently
- Aggregation overhead: Minimal (<50ms for global, <100ms for per_repo)
- Network latency: Dominant factor in multi-repository searches

**Performance Tips**:
- Use language/path filters to reduce search scope per repository
- Start with limit=5-10 to conserve context tokens
- Consider aggregation_mode based on result distribution needs
- Use global mode when quality matters most
- Use per_repo mode when repository representation matters

### Response Format

Multi-repository search results include a source_repo field identifying the origin repository:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "results": [
      {
        "file_path": "src/auth/jwt.py",
        "source_repo": "backend-global",
        "score": 0.89,
        "content": "...",
        "language": "python"
      },
      {
        "file_path": "src/authentication.ts",
        "source_repo": "frontend-global",
        "score": 0.85,
        "content": "...",
        "language": "typescript"
      }
    ],
    "total_results": 25,
    "repositories_searched": ["backend-global", "frontend-global", "auth-service-global"]
  },
  "id": 1
}
```

**Response Fields**:
- `source_repo`: Repository alias where result originated
- `repositories_searched`: List of all repositories included in search
- `total_results`: Total matches found across all repositories
- All other fields identical to single-repository searches

### Supported Tools

Omni-search is available in the following MCP tools:

1. **search_code**: Semantic, FTS, regex, hybrid, and temporal searches
2. **list_files**: Directory listings across multiple repositories
3. **regex_search**: Pattern-based file searches across repositories
4. **git_log**: Git history from multiple repositories
5. **git_search_commits**: Commit message searches across repositories

All tools support both aggregation_mode options and the source_repo response field.

### Filtering Across Repositories

All standard filters work with multi-repository searches:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "database migration",
      "repository_alias": ["backend-global", "api-global", "worker-global"],
      "language": "python",
      "path_filter": "*/migrations/*",
      "exclude_path": "*/tests/*",
      "aggregation_mode": "global",
      "limit": 20
    }
  },
  "id": 1
}' | cidx-bridge
```

Filters apply to each repository independently before aggregation.

### Best Practices

**When to use global aggregation**:
- Quality-focused searches (need best matches)
- Cross-repository code analysis
- Finding canonical implementations
- Security-critical code discovery

**When to use per_repo aggregation**:
- Comparative analysis across services
- Ensuring representation from all codebases
- Code review across multiple repositories
- Understanding implementation differences

**Performance optimization**:
- Use specific language/path filters to narrow scope
- Start with small limits (5-10) for exploration
- Consider repository count vs query complexity tradeoff
- Use per_repo mode when repository balance matters more than absolute quality

## Error Handling

### Invalid Parameter Error

Request with invalid search_mode:

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test",
      "search_mode": "invalid"
    }
  },
  "id": 1
}' | cidx-bridge
```

Response:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params: search_mode must be one of: semantic, fts, hybrid"
  },
  "id": 1
}
```

### Incompatible Parameters

Request with fuzzy + regex (incompatible):

```bash
echo '{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search_code",
    "arguments": {
      "query_text": "test",
      "search_mode": "fts",
      "fuzzy": true,
      "regex": true
    }
  },
  "id": 1
}' | cidx-bridge
```

Response:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params: fuzzy and regex are mutually exclusive"
  },
  "id": 1
}
```

## Next Steps

- See [API Reference](api-reference.md) for complete parameter documentation
- See [Troubleshooting Guide](troubleshooting.md) for problem resolution
- See [Setup Guide](setup.md) for installation and configuration

## Version Information

- MCPB version: 8.1.0
- search_code tool: src/code_indexer/server/mcp/tools.py:9-147
- Total parameters: 25 (verified)
- Omni-search support: 5 tools (search_code, list_files, regex_search, git_log, git_search_commits)

Last Updated: 2025-12-06
