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

Last Updated: 2025-11-26
