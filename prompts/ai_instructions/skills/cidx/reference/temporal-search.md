# Temporal Search - Git History and Code Archaeology

Temporal search analyzes git history to find when code was added, track bug evolution, search commit messages, and understand feature development over time.

## Overview

Temporal search enables code archaeology across git history:
- **When was X added?** - Find when functionality was introduced
- **Bug history** - Track how bugs evolved and were fixed
- **Feature evolution** - Understand how features developed over time
- **Author work** - Find specific developer's contributions

## Prerequisites

**CRITICAL**: Temporal search requires indexing git commits first.

```bash
# Index commits (required first step)
cidx index --index-commits

# Verify indexing completed
cidx query "test query" --time-range-all --quiet
```

Without `--index-commits`, temporal search will return no results.

## Indexing Git History

### Basic Indexing

```bash
# Index commits for temporal search
cidx index --index-commits

# This creates temporal chunks for:
# - Commit messages
# - Commit diffs (code changes)
# - Author metadata
```

### Advanced Indexing Options

```bash
# Index all branches (not just current)
cidx index --index-commits --all-branches

# Limit number of commits indexed
cidx index --index-commits --max-commits 1000

# Index commits since specific date
cidx index --index-commits --since-date 2024-01-01

# Combine options
cidx index --index-commits --all-branches --since-date 2024-01-01 --max-commits 500
```

### Indexing Flags

- `--index-commits` - Enable commit indexing (REQUIRED)
- `--all-branches` - Index commits from all branches (default: current branch only)
- `--max-commits N` - Limit to N most recent commits (default: unlimited)
- `--since-date YYYY-MM-DD` - Index commits since date (default: all history)

**Performance Notes**:
- First-time indexing can take time for large repositories
- Incremental re-indexing is faster (only new commits)
- Use `--max-commits` or `--since-date` for large repos

## Temporal Query Flags

### Time Range Selection

- `--time-range-all` - Search all indexed commits
  - Most common temporal search flag
  - Example: `cidx query "JWT auth" --time-range-all --quiet`

- `--time-range YYYY-MM-DD..YYYY-MM-DD` - Search specific date range
  - Inclusive range
  - Example: `cidx query "security" --time-range 2024-01-01..2024-12-31 --quiet`

### Chunk Type Selection

- `--chunk-type commit_message` - Search only commit messages
  - Fast, focused on commit descriptions
  - Example: `cidx query "fix bug" --time-range-all --chunk-type commit_message --quiet`

- `--chunk-type commit_diff` - Search only code changes (diffs)
  - Slower, searches actual code modifications
  - Example: `cidx query "authentication" --time-range-all --chunk-type commit_diff --quiet`

- Default (no `--chunk-type`): Search both messages and diffs

### Author Filtering

- `--author EMAIL` - Filter by commit author email
  - Example: `cidx query "refactor" --time-range-all --author "dev@company.com" --quiet`

## Use Cases and Examples

### 1. When Was X Added? (Code Archaeology)

**Find when functionality was introduced**:

```bash
# When was JWT authentication added?
cidx query "JWT authentication" --time-range-all --quiet

# When was specific class introduced?
cidx query "UserService class" --time-range-all --chunk-type commit_diff --quiet

# When was configuration system added?
cidx query "configuration system" --time-range-all --quiet
```

**Narrow by date range**:
```bash
# Check if feature added in 2024
cidx query "payment gateway" --time-range 2024-01-01..2024-12-31 --quiet

# Check recent additions (last 6 months)
cidx query "API endpoint" --time-range 2024-06-01..2024-12-31 --quiet
```

### 2. Bug History and Fixes

**Track bug evolution**:

```bash
# Find all bug-related commits
cidx query "bug fix" --time-range-all --chunk-type commit_message --quiet

# Find specific bug fixes
cidx query "authentication bug" --time-range-all --chunk-type commit_message --quiet

# Search for security fixes
cidx query "security vulnerability fix" --time-range-all --quiet
```

**Investigate bug patterns**:
```bash
# Find when similar bugs occurred
cidx query "null pointer exception" --time-range-all --quiet

# Track regression fixes
cidx query "regression" --time-range-all --chunk-type commit_message --quiet

# Find emergency hotfixes
cidx query "hotfix critical" --time-range-all --chunk-type commit_message --quiet
```

### 3. Feature Evolution

**Understand feature development over time**:

```bash
# Track authentication feature development
cidx query "authentication" --time-range-all --quiet

# See how API evolved
cidx query "REST API" --time-range-all --chunk-type commit_message --quiet

# Track refactoring efforts
cidx query "refactor" --time-range-all --chunk-type commit_message --quiet
```

**Analyze specific periods**:
```bash
# What changed in Q1 2024?
cidx query "feature" --time-range 2024-01-01..2024-03-31 --quiet

# Development during sprint
cidx query "implement" --time-range 2024-11-01..2024-11-30 --quiet
```

### 4. Author Work History

**Find specific developer's contributions**:

```bash
# All work by specific author
cidx query "feature" --time-range-all --author "alice@company.com" --quiet

# Author's refactoring work
cidx query "refactor" --time-range-all --author "bob@company.com" --quiet

# Security fixes by author
cidx query "security" --time-range-all --author "security@company.com" --quiet
```

**Combine with date ranges**:
```bash
# Author's work in specific period
cidx query "implement" \
  --time-range 2024-01-01..2024-12-31 \
  --author "dev@company.com" \
  --quiet

# Recent contributions
cidx query "add" \
  --time-range 2024-11-01..2024-12-31 \
  --author "alice@company.com" \
  --quiet
```

### 5. Commit Message Search

**Search commit messages specifically**:

```bash
# Find breaking changes
cidx query "breaking change" --time-range-all --chunk-type commit_message --quiet

# Find merge commits
cidx query "merge" --time-range-all --chunk-type commit_message --quiet

# Find release commits
cidx query "release" --time-range-all --chunk-type commit_message --quiet

# Find dependency updates
cidx query "update dependencies" --time-range-all --chunk-type commit_message --quiet
```

### 6. Code Change Search (Diffs)

**Search actual code modifications**:

```bash
# Find when specific function was modified
cidx query "authenticate_user" --time-range-all --chunk-type commit_diff --quiet

# Find database schema changes
cidx query "ALTER TABLE" --time-range-all --chunk-type commit_diff --quiet

# Find API signature changes
cidx query "function signature" --time-range-all --chunk-type commit_diff --quiet
```

## Combining Temporal with Other Filters

Temporal search works with all standard filters:

```bash
# Temporal + language filter
cidx query "authentication" \
  --time-range-all \
  --language python \
  --quiet

# Temporal + path filter
cidx query "bug fix" \
  --time-range-all \
  --path-filter "src/backend/*" \
  --quiet

# Temporal + limit
cidx query "refactor" \
  --time-range-all \
  --limit 10 \
  --quiet

# Full combination
cidx query "security fix" \
  --time-range 2024-01-01..2024-12-31 \
  --chunk-type commit_message \
  --author "security@company.com" \
  --language python \
  --limit 5 \
  --quiet
```

## Workflow Examples

### Investigating When Feature Was Added

```bash
# 1. Broad search across all history
cidx query "OAuth integration" --time-range-all --quiet

# 2. Narrow to commit messages
cidx query "OAuth" --time-range-all --chunk-type commit_message --quiet

# 3. Check code changes
cidx query "OAuth" --time-range-all --chunk-type commit_diff --quiet

# 4. Identify specific period
cidx query "OAuth" --time-range 2024-01-01..2024-06-30 --quiet
```

### Tracking Bug Fix History

```bash
# 1. Find all related bug commits
cidx query "authentication bug" --time-range-all --chunk-type commit_message --quiet

# 2. Check when bug was introduced
cidx query "authentication error" --time-range-all --chunk-type commit_diff --quiet

# 3. Find who fixed it
cidx query "fix authentication" \
  --time-range-all \
  --chunk-type commit_message \
  --quiet

# 4. Verify the fix in code
cidx query "authentication fix" --time-range-all --chunk-type commit_diff --quiet
```

### Understanding Team Contributions

```bash
# 1. All commits by team member
cidx query "implement" --time-range-all --author "alice@company.com" --quiet

# 2. Specific feature work
cidx query "payment" --time-range-all --author "alice@company.com" --quiet

# 3. During specific sprint
cidx query "feature" \
  --time-range 2024-11-01..2024-11-30 \
  --author "alice@company.com" \
  --quiet

# 4. Focus on commit messages
cidx query "add" \
  --time-range-all \
  --author "alice@company.com" \
  --chunk-type commit_message \
  --quiet
```

## Best Practices

### 1. Index Commits First
```bash
# Always run this before temporal queries
cidx index --index-commits
```

### 2. Start with Commit Messages
```bash
# Faster, more targeted
cidx query "bug fix" --time-range-all --chunk-type commit_message --quiet
```

### 3. Use Time Ranges to Narrow Scope
```bash
# Don't search all history if you know timeframe
cidx query "feature" --time-range 2024-01-01..2024-12-31 --quiet
```

### 4. Combine with Author for Team Analysis
```bash
# Focus on specific developer's work
cidx query "refactor" --time-range-all --author "dev@company.com" --quiet
```

### 5. Use Limits for Large Results
```bash
# Prevent overwhelming output
cidx query "fix" --time-range-all --limit 10 --quiet
```

## Indexing Strategies

### For Large Repositories

```bash
# Index recent commits only (last year)
cidx index --index-commits --since-date 2024-01-01

# Limit to most recent 1000 commits
cidx index --index-commits --max-commits 1000

# Index current branch only (default)
cidx index --index-commits
```

### For Multi-Branch Projects

```bash
# Index all branches
cidx index --index-commits --all-branches

# Index specific recent commits across all branches
cidx index --index-commits --all-branches --since-date 2024-01-01
```

### For Continuous Integration

```bash
# Fast incremental indexing (only new commits)
cidx index --index-commits --since-date 2024-11-01

# Limit commits for CI performance
cidx index --index-commits --max-commits 100
```

## Troubleshooting

### No Results Found

**Check if commits indexed**:
```bash
# Verify indexing
cidx query "test" --time-range-all --quiet

# Re-index if necessary
cidx index --index-commits
```

**Try broader query**:
```bash
# Remove chunk type filter
cidx query "authentication" --time-range-all --quiet

# Expand time range
cidx query "bug" --time-range 2023-01-01..2024-12-31 --quiet
```

### Too Many Results

**Add chunk type filter**:
```bash
# Search only commit messages
cidx query "fix" --time-range-all --chunk-type commit_message --quiet
```

**Narrow time range**:
```bash
# Specific year
cidx query "feature" --time-range 2024-01-01..2024-12-31 --quiet

# Recent commits
cidx query "add" --time-range 2024-11-01..2024-12-31 --quiet
```

**Add author filter**:
```bash
# Specific developer
cidx query "implement" --time-range-all --author "dev@company.com" --quiet
```

**Use limit**:
```bash
# Cap results
cidx query "refactor" --time-range-all --limit 5 --quiet
```

### Performance Issues

**Reduce scope**:
```bash
# Shorter time range
cidx query "bug" --time-range 2024-06-01..2024-12-31 --quiet

# Commit messages only (faster)
cidx query "fix" --time-range-all --chunk-type commit_message --limit 10 --quiet
```

**Optimize indexing**:
```bash
# Index recent commits only
cidx index --index-commits --since-date 2024-01-01

# Limit commits indexed
cidx index --index-commits --max-commits 500
```

## When to Use Temporal Search

| Use Case | Use Temporal | Example |
|----------|--------------|---------|
| When was X added? | ✅ | `--time-range-all` |
| Bug fix history | ✅ | `--chunk-type commit_message` |
| Feature evolution | ✅ | `--time-range YYYY-MM-DD..YYYY-MM-DD` |
| Author contributions | ✅ | `--author email` |
| Current code search | ❌ | Use semantic/FTS instead |
| Live code understanding | ❌ | Use semantic search |
| Exact current identifiers | ❌ | Use FTS |
