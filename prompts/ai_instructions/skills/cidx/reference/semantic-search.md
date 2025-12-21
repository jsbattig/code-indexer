# Semantic Search - Code Understanding and Discovery

Semantic search finds code based on meaning and behavior, not just exact text matches. Use this when you want to understand "what code does" or "where is X implemented".

## Decision Rule

**Use semantic search when**:
- "What code does X" - Understanding functionality
- "Where is X implemented" - Finding implementations
- "How does the system handle Y" - Discovering behavior patterns
- "Show me authentication code" - Broad concept search

**Do NOT use semantic search when**:
- Exact text (identifiers, function names) → Use `--fts` instead
- Pattern matching (regex) → Use `--fts --regex` instead

## Basic Usage

```bash
cidx query "authentication" --quiet
cidx query "database connection pooling" --quiet
cidx query "error handling middleware" --quiet
```

## Key Flags

### Result Control
- `--limit N` - Maximum results (default 10)
  - **Context conservation**: Start with 5-10 to conserve context window
  - High limits consume context rapidly when results contain large code files
  - Example: `cidx query "auth" --limit 5 --quiet`

- `--quiet` - Minimal output (ALWAYS use this)
  - Suppresses progress bars and verbose logging
  - Essential for clean output in AI assistant workflows

### Language Filtering
- `--language LANG` - Filter by programming language
  - Common values: python, typescript, java, kotlin, go, rust
  - Example: `cidx query "authentication" --language python --quiet`

- `--exclude-language LANG` - Exclude specific languages
  - Useful for multi-language projects
  - Example: `cidx query "config" --exclude-language javascript --quiet`

### Path Filtering
- `--path-filter PATTERN` - Include only matching paths
  - Glob patterns: `*/tests/*`, `src/auth/*`, `backend/**`
  - Example: `cidx query "validation" --path-filter "*/tests/*" --quiet`

- `--exclude-path PATTERN` - Exclude matching paths
  - Common: `--exclude-path "*/tests/*"` to exclude test files
  - Example: `cidx query "auth" --exclude-path "*/node_modules/*" --quiet`

### Accuracy and Scoring
- `--min-score FLOAT` - Minimum similarity threshold (0.0-1.0)
  - Higher values = more precise but fewer results
  - Default: 0.7
  - Example: `cidx query "auth" --min-score 0.8 --quiet`

- `--accuracy high|medium|low` - Search precision
  - `high` - More precise, slower, fewer false positives
  - `medium` - Balanced (default)
  - `low` - Faster, more results, more noise
  - Example: `cidx query "config" --accuracy high --quiet`

### File Extensions
- `--file-extensions EXT1,EXT2` - Limit to specific extensions
  - Example: `cidx query "validation" --file-extensions py,js --quiet`

## Context Conservation Guidance

**Critical for AI assistants**: Large result sets consume context window rapidly.

**Best Practices**:
1. **Start small**: `--limit 5` for initial queries
2. **Filter aggressively**: Use `--language` and `--path-filter` to narrow scope
3. **Exclude noise**: `--exclude-path "*/tests/*"` for production code focus
4. **Iterate**: Refine query with filters if initial results are too broad

**Example progressive refinement**:
```bash
# Initial broad search (5 results)
cidx query "authentication" --limit 5 --quiet

# Too many test files - exclude tests
cidx query "authentication" --limit 5 --exclude-path "*/tests/*" --quiet

# Focus on Python only
cidx query "authentication" --language python --limit 5 --exclude-path "*/tests/*" --quiet

# Increase limit after narrowing scope
cidx query "authentication" --language python --limit 10 --exclude-path "*/tests/*" --quiet
```

## Practical Examples

### Finding Authentication Code
```bash
# Broad search for auth logic
cidx query "user authentication and login" --language python --quiet

# Focus on backend auth only
cidx query "authentication" --path-filter "backend/*" --language python --quiet

# Exclude test files
cidx query "authentication" --exclude-path "*/tests/*" --language python --quiet
```

### Database Operations
```bash
# Find database connection handling
cidx query "database connection pooling" --language python --limit 5 --quiet

# Find migration code
cidx query "database schema migration" --path-filter "*/migrations/*" --quiet

# Find ORM usage
cidx query "database query and orm" --exclude-path "*/tests/*" --quiet
```

### Error Handling
```bash
# Find error handling patterns
cidx query "error handling and exception management" --language typescript --quiet

# Focus on middleware
cidx query "error middleware" --path-filter "*/middleware/*" --quiet

# High-precision search
cidx query "custom error classes" --accuracy high --min-score 0.8 --quiet
```

### API Routes
```bash
# Find REST API endpoints
cidx query "REST API routes and handlers" --language typescript --quiet

# Focus on specific API domain
cidx query "user API endpoints" --path-filter "*/api/users/*" --quiet

# Exclude generated code
cidx query "API routes" --exclude-path "*/generated/*" --quiet
```

## Combining Filters

Filters can be combined for powerful targeted searches:

```bash
# Python auth code, no tests, high precision, limit to backend
cidx query "authentication" \
  --language python \
  --exclude-path "*/tests/*" \
  --path-filter "backend/*" \
  --accuracy high \
  --min-score 0.8 \
  --limit 10 \
  --quiet

# TypeScript validation logic in services layer only
cidx query "input validation" \
  --language typescript \
  --path-filter "*/services/*" \
  --exclude-path "*/node_modules/*" \
  --limit 5 \
  --quiet
```

## When to Switch to Other Search Modes

**Switch to FTS (full-text search)** when you need:
- Exact function/class names: `cidx query "UserService" --fts --quiet`
- TODO comments: `cidx query "TODO" --fts --case-sensitive --quiet`
- Specific identifiers: `cidx query "authenticate_user" --fts --quiet`

**Switch to FTS + Regex** when you need:
- Pattern matching: `cidx query "test_.*" --fts --regex --quiet`
- Token-based search: `cidx query "def.*auth" --fts --regex --quiet`

**Switch to Temporal Search** when you need:
- Code history: `cidx query "JWT auth" --time-range-all --quiet`
- Bug archaeology: `cidx query "security fix" --time-range-all --chunk-type commit_message --quiet`

## Troubleshooting

### Too Many Results
- Decrease `--limit` to fewer results
- Add `--language` filter to focus on one language
- Use `--path-filter` to narrow to specific directories
- Increase `--min-score` to raise similarity threshold
- Use `--accuracy high` for more precision

### Too Few Results
- Increase `--limit` to see more candidates
- Remove restrictive filters (`--language`, `--path-filter`)
- Lower `--min-score` to broaden similarity matching
- Use `--accuracy low` for wider net
- Try different query phrasing (e.g., "user login" vs "authentication")

### Irrelevant Results
- Increase `--min-score` threshold (try 0.8 or 0.9)
- Use `--accuracy high` for precision
- Add domain-specific terms to query (e.g., "JWT authentication" instead of "authentication")
- Use `--exclude-path` to remove noisy directories

### Performance Issues
- Reduce `--limit` to fetch fewer results
- Use `--language` to limit to one language
- Use `--path-filter` to narrow search scope
- Consider indexing if not already done: `cidx index`
