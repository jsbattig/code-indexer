# Temporal Search - Git History Search

Search your entire git commit history semantically with CIDX temporal queries.

## Table of Contents

- [Overview](#overview)
- [Setup](#setup)
- [Basic Usage](#basic-usage)
- [Query Parameters](#query-parameters)
- [Use Cases](#use-cases)
- [Examples](#examples)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)

## Overview

Temporal search allows you to **semantically search your git history** - find when code was added, modified, or deleted based on conceptual queries, not just text matching.

**What Makes It Unique**:
- **Semantic search** across commits and diffs (not just grep)
- **Time-range filtering** - search specific date ranges
- **Author filtering** - find changes by specific developers
- **Diff type filtering** - added, modified, deleted, renamed, binary
- **Chunk type selection** - search commit messages or code diffs

**Use Cases**:
- Code archaeology - "When was OAuth added?"
- Bug history - "Find security patches from last quarter"
- Feature evolution - "How did authentication change over time?"
- Author analysis - "What did the security team work on?"

## Setup

### 1. Index Git Commits

Temporal search requires indexing your git history first:

```bash
# One-time setup (indexes all commits)
cidx index --index-commits

# This creates temporal indexes in:
# .code-indexer/index/code-indexer-temporal/temporal_meta.json
```

**What Gets Indexed**:
- Commit messages (semantic vectors)
- Code diffs (semantic vectors)
- Commit metadata (author, date, hash)
- Diff types (added/modified/deleted/renamed/binary)

**Indexing Time**:
- Small repos (<100 commits): Seconds
- Medium repos (100-1000 commits): 1-5 minutes
- Large repos (1000+ commits): 5-30 minutes

### 2. Verify Temporal Index

```bash
# Check if temporal index exists
ls -lh .code-indexer/index/code-indexer-temporal/temporal_meta.json

# Should see temporal_meta.json file in the code-indexer-temporal collection
```

## Basic Usage

### Simple Temporal Search

```bash
# Search all git history
cidx query "JWT authentication" --time-range-all --quiet

# Always use --quiet for cleaner output
```

**Output**:
- Commits containing matching code/messages
- File paths and line numbers
- Commit hashes and authors
- Timestamps

### Time Range Search

```bash
# Specific date range (YYYY-MM-DD..YYYY-MM-DD)
cidx query "security fix" --time-range 2024-01-01..2024-12-31 --quiet

# Last quarter
cidx query "refactoring" --time-range 2024-10-01..2024-12-31 --quiet

# Specific month
cidx query "new feature" --time-range 2024-11-01..2024-11-30 --quiet
```

## Query Parameters

### Core Temporal Parameters

| Parameter | CLI Flag | Type | Description |
|-----------|----------|------|-------------|
| **time_range** | --time-range RANGE | string | Date range (YYYY-MM-DD..YYYY-MM-DD) |
| **time_range_all** | --time-range-all | flag | Search all git history |
| **diff_type** | --diff-type TYPE | string | Filter by diff type |
| **author** | --author NAME | string | Filter by commit author |
| **chunk_type** | --chunk-type TYPE | enum | commit_message or commit_diff |

**Note**: Always use `--quiet` flag with temporal queries for cleaner output.

### API-Only Parameters

These parameters are only available via REST/MCP API (not CLI):

| Parameter | Type | Description |
|-----------|------|-------------|
| **at_commit** | string | Query code at specific commit hash |
| **include_removed** | boolean | Include files removed from HEAD |
| **show_evolution** | boolean | Show code evolution timeline |
| **evolution_limit** | integer | Limit evolution entry count |

### Time Range Format

```bash
# Full date range
--time-range 2024-01-01..2024-12-31

# All history
--time-range-all
```

**Date Format**: YYYY-MM-DD (ISO 8601)

### Diff Types

| Type | Description | Use Case |
|------|-------------|----------|
| **added** | Newly added code | "When was feature X added?" |
| **modified** | Changed code | "Recent changes to auth module" |
| **deleted** | Removed code | "What was removed during refactor?" |
| **renamed** | Renamed files | "File name changes" |
| **binary** | Binary file changes | "Binary asset updates" |

```bash
# Find when code was added
cidx query "OAuth integration" --time-range-all --diff-type added --quiet

# Find modifications
cidx query "password validation" --time-range-all --diff-type modified --quiet

# Find deletions
cidx query "legacy code" --time-range-all --diff-type deleted --quiet
```

**Multiple Diff Types** (API only):
```json
{
  "diff_type": "added,modified"
}
```

### Author Filtering

```bash
# Filter by email
cidx query "feature work" --time-range-all --author "dev@example.com" --quiet

# Filter by name (partial match)
cidx query "bug fixes" --time-range-all --author "John" --quiet

# Filter by team alias
cidx query "security updates" --time-range-all --author "security-team" --quiet
```

**Author Matching**:
- Matches commit author name OR email
- Partial matches supported ("John" matches "John Doe", "johnny@example.com")
- Case-insensitive

### Chunk Types

| Type | Description | Use Case |
|------|-------------|----------|
| **commit_message** | Search commit messages only | Find tickets, keywords in messages |
| **commit_diff** | Search code diffs only | Find code changes, not messages |

```bash
# Search commit messages (find tickets, keywords)
cidx query "JIRA-123" --time-range-all --chunk-type commit_message --quiet

# Search code diffs (find actual code changes)
cidx query "authentication logic" --time-range-all --chunk-type commit_diff --quiet
```

**Default**: Both commit messages and diffs are searched if chunk_type not specified.

## Use Cases

### 1. Code Archaeology

**"When was this feature added?"**

```bash
# Find when JWT authentication was added
cidx query "JWT token validation" --time-range-all --diff-type added --quiet

# Find initial OAuth implementation
cidx query "OAuth integration" --time-range-all --diff-type added --quiet
```

### 2. Bug History Tracking

**"Find all security patches from last quarter"**

```bash
# Security fixes in Q4 2024
cidx query "security vulnerability fix" \
  --time-range 2024-10-01..2024-12-31 \
  --chunk-type commit_message \
  --quiet

# Find XSS patch commits
cidx query "XSS protection" --time-range-all --diff-type modified --quiet
```

### 3. Feature Evolution

**"How did authentication change over time?"**

```bash
# Find all authentication-related commits
cidx query "authentication" --time-range-all --quiet

# Find auth changes in 2024
cidx query "authentication" --time-range 2024-01-01..2024-12-31 --quiet

# Find auth refactoring
cidx query "auth refactor" --time-range-all --chunk-type commit_message --quiet
```

### 4. Author Analysis

**"What did the security team work on?"**

```bash
# All security team commits
cidx query "security" --time-range-all --author "security-team" --quiet

# Specific developer's work
cidx query "feature implementation" --time-range-all --author "jane@example.com" --quiet

# Team contributions in date range
cidx query "new features" \
  --time-range 2024-11-01..2024-11-30 \
  --author "backend-team" \
  --quiet
```

### 5. Refactoring Analysis

**"What was removed during the refactor?"**

```bash
# Find deleted code
cidx query "legacy authentication" --time-range-all --diff-type deleted --quiet

# Find refactoring commits
cidx query "refactor" --time-range 2024-01-01..2024-12-31 \
  --chunk-type commit_message \
  --quiet
```

### 6. Ticket/Issue Tracking

**"Find all work related to JIRA-123"**

```bash
# Search commit messages for ticket number
cidx query "JIRA-123" --time-range-all --chunk-type commit_message --quiet

# Find related code changes
cidx query "JIRA-123" --time-range-all --chunk-type commit_diff --quiet
```

## Examples

### Combine Multiple Filters

```bash
# Complex temporal query:
# Find auth changes by security team in Q4 2024
cidx query "authentication" \
  --time-range 2024-10-01..2024-12-31 \
  --author "security-team@example.com" \
  --diff-type modified \
  --chunk-type commit_diff \
  --language python \
  --quiet
```

### Recent Changes

```bash
# Find changes from last 30 days
cidx query "bug fix" --time-range 2024-12-01..2024-12-31 --quiet

# Find this month's features
cidx query "new feature" --time-range 2024-12-01..2024-12-31 \
  --chunk-type commit_message \
  --quiet
```

### Specific File History

```bash
# Combine with path filtering
cidx query "auth changes" \
  --time-range-all \
  --path-filter "*/auth/*" \
  --quiet
```

## Performance

### Indexing Performance

| Repository Size | Commits | Index Time |
|----------------|---------|------------|
| Small | <100 | <30 seconds |
| Medium | 100-1000 | 1-5 minutes |
| Large | 1000-10000 | 5-30 minutes |
| Very Large | 10000+ | 30+ minutes |

**Optimization Tips**:
- Index once, query many times
- Incremental indexing updates only new commits
- Use `--index-commits` on initial setup only

### Query Performance

| Query Type | Performance | Notes |
|------------|-------------|-------|
| **Simple temporal** | ~200-500ms | All history, no filters |
| **Time range** | ~100-300ms | Filtered by date |
| **With author filter** | ~150-400ms | Additional filtering |
| **Complex (multiple filters)** | ~300-800ms | Multiple filter overhead |

**Performance Factors**:
- Repository size (commit count)
- Time range breadth
- Number of filters applied
- Semantic complexity of query

### Storage Impact

Temporal indexing increases storage:

| Repository | Additional Storage |
|------------|-------------------|
| Small (<100 commits) | ~1-5 MB |
| Medium (100-1000) | ~5-50 MB |
| Large (1000-10000) | ~50-500 MB |
| Very Large (10000+) | ~500MB-2GB |

**Storage Location**: `.code-indexer/index/code-indexer-temporal/` (includes temporal_meta.json, HNSW index, ID index, quantized vectors)

## Troubleshooting

### No Temporal Results

**Symptom**: Query returns 0 results or "temporal index not found"

**Solutions**:

1. **Verify temporal index exists**:
   ```bash
   ls -lh .code-indexer/index/code-indexer-temporal/temporal_meta.json
   ```

2. **Index commits if missing**:
   ```bash
   cidx index --index-commits
   ```

3. **Try broader query**:
   ```bash
   # Start with --time-range-all and no filters
   cidx query "anything" --time-range-all --quiet
   ```

### Slow Temporal Queries

**Causes**:
- Very large commit history
- Broad time range
- Complex semantic query

**Solutions**:

```bash
# Narrow time range
cidx query "feature" --time-range 2024-11-01..2024-11-30 --quiet

# Add author filter
cidx query "feature" --time-range-all --author "specific-dev" --quiet

# Use chunk type to narrow scope
cidx query "feature" --time-range-all --chunk-type commit_message --quiet
```

### Temporal Index Outdated

**Symptom**: Recent commits not showing in results

**Solution**:
```bash
# Reindex to include latest commits
cidx index --index-commits

# This incrementally updates the temporal index
```

### Wrong Chunk Type

**Symptom**: Expected results not found

**Check**:
- Use `commit_message` for ticket numbers, keywords in messages
- Use `commit_diff` for actual code changes
- Omit `--chunk-type` to search both

```bash
# Search both messages and diffs (default)
cidx query "OAuth" --time-range-all --quiet

# Search only messages
cidx query "JIRA-123" --time-range-all --chunk-type commit_message --quiet

# Search only code
cidx query "authentication logic" --time-range-all --chunk-type commit_diff --quiet
```

### Memory Issues During Indexing

**Symptom**: Out of memory error during `cidx index --index-commits`

**Solutions**:

1. **Increase available memory** (if possible)

2. **Index in smaller batches** (not currently supported - would need implementation)

3. **Exclude large binary files**:
   ```bash
   # Add to .gitignore before indexing
   echo "*.mp4" >> .gitignore
   echo "*.zip" >> .gitignore
   ```

---

## Next Steps

- **Query Guide**: [Complete Query Reference](query-guide.md)
- **Operating Modes**: [Operating Modes Guide](operating-modes.md)
- **Installation**: [Installation Guide](installation.md)
- **Main Documentation**: [README](../README.md)

---

## Related Documentation

- **Architecture**: [Architecture Guide](architecture.md)
- **SCIP**: [SCIP Code Intelligence](scip/README.md)
- **Configuration**: [Configuration Guide](configuration.md)

---

