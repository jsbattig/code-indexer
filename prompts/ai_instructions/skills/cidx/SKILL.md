---
name: cidx
description: Code search and intelligence using CIDX. Use when searching codebases, finding implementations, tracing call graphs, analyzing dependencies, or searching git history. Preferred over grep/find for all code exploration.
---

# CIDX - Semantic Code Search and Intelligence

Comprehensive CIDX (Code Indexer) documentation for AI coding assistants.

## SEMANTIC SEARCH - MANDATORY FIRST ACTION

**CIDX FIRST**: Always use `cidx query` before grep/find/rg for semantic searches.

**Decision Rule**:
- "What code does", "Where is X implemented" → CIDX semantic (default)
- Exact text (identifiers, function names) → `--fts`
- Pattern matching (regex) → `--fts --regex` (10-50x faster than grep)
- CIDX unavailable → grep/find (fallback only)

**Key Flags**: `--limit N` (default 10, start with 5-10 to conserve context) | `--language python` | `--path-filter */tests/*` | `--exclude-path PATTERN` | `--exclude-language LANG` | `--min-score 0.8` | `--accuracy high` | `--quiet`

**Context Conservation**: Start with low `--limit` values (5-10) on initial queries. High limits consume context window rapidly when results contain large code files.

**Example**: `cidx query "authentication" --language python --exclude-path "*/tests/*" --limit 5 --quiet`

---

## FULL-TEXT SEARCH (FTS)

**Use For**: Exact names, identifiers, TODO comments, typo debugging.

**Flags**: `--fts` | `--case-sensitive` | `--fuzzy` | `--edit-distance N` | `--snippet-lines N`

**Example**: `cidx query "authenticate_user" --fts --case-sensitive --quiet`

**Hybrid**: `--fts --semantic` runs both in parallel.

---

## REGEX MODE (Grep Replacement)

**Flags**: `--fts --regex` | Incompatible with `--semantic` and `--fuzzy`

**Token-Based**: Matches individual tokens only.
- Works: `def`, `login.*`, `test_.*`
- Doesn't work: `def\s+\w+` (whitespace removed)

**Example**: `cidx query "def.*auth" --fts --regex --language python --quiet`

**Fallback**: Use grep only when CIDX unavailable.

---

## TEMPORAL SEARCH (Git History)

**Use For**: Code archaeology, commit message search, bug history, feature evolution.

**Indexing**: `cidx index --index-commits` (required first)

**Flags**: `--time-range-all` | `--time-range YYYY-MM-DD..YYYY-MM-DD` | `--chunk-type commit_message` | `--chunk-type commit_diff` | `--author EMAIL`

**Examples**:
- When added: `cidx query "JWT auth" --time-range-all --quiet`
- Bug history: `cidx query "database bug" --time-range-all --chunk-type commit_message --quiet`
- Author work: `cidx query "refactor" --time-range-all --author "dev@company.com" --quiet`

**Indexing Options**: `--all-branches` | `--max-commits N` | `--since-date YYYY-MM-DD`

---

## SCIP CALL GRAPH AND DEPENDENCY ANALYSIS

CIDX provides precise code intelligence via SCIP (Source Code Intelligence Protocol) indexes.

**For complete SCIP documentation**: See reference/scip-intelligence.md

**Quick reference - SCIP commands**:
- `cidx scip definition SYMBOL` - Find where a symbol is defined
- `cidx scip references SYMBOL` - Find all references to a symbol
- `cidx scip dependencies SYMBOL` - Get symbols this symbol depends on
- `cidx scip dependents SYMBOL` - Get symbols that depend on this symbol
- `cidx scip callchain FROM TO` - Trace call chains between symbols
- `cidx scip context SYMBOL` - Get smart context (curated file list)
- `cidx scip impact SYMBOL` - Analyze change impact

**SCIP index generation**:
```bash
cidx scip generate           # Generate SCIP indexes for all projects
cidx scip status             # Show generation status
cidx scip rebuild PROJECT    # Rebuild specific project
```

---

## REFERENCE DOCUMENTATION

Detailed documentation available in reference/ directory:
- reference/scip-intelligence.md - Complete SCIP call graph and dependency analysis guide
