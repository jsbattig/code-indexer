# SCIP Intelligence - Call Graph and Dependency Analysis

Complete guide to CIDX SCIP (Source Code Intelligence Protocol) commands for precise code navigation, call graph analysis, and dependency tracking.

## Overview

SCIP provides language-agnostic code intelligence beyond semantic search. It enables precise navigation, dependency analysis, and impact assessment across Java, Kotlin, TypeScript, and Python projects.

## Prerequisites

SCIP indexes must be generated before using query commands:

```bash
cidx scip generate           # Generate indexes for all discovered projects
cidx scip status             # Verify generation status
```

Indexes are stored in `.code-indexer/scip/` directory.

---

## Query Commands

### 1. Definition - Find Symbol Definitions

Find where a symbol is defined (classes, methods, functions, variables).

**Usage**:
```bash
cidx scip definition SYMBOL [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--exact` - Match exact symbol name (no substring matching)
- `--project TEXT` - Limit search to specific project path

**Examples**:
```bash
cidx scip definition UserService            # Find UserService definitions
cidx scip definition authenticate           # Find authenticate method
cidx scip definition UserService --exact    # Exact match only
cidx scip definition Config --project backend/  # Search only in backend
```

**When to use**:
- Finding class/function definitions
- Navigating to implementation from usage
- Discovering symbol locations across multi-module projects

---

### 2. References - Find Symbol Usages

Find all references to a symbol (where it's used/imported/called).

**Usage**:
```bash
cidx scip references SYMBOL [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--exact` - Match exact symbol name
- `--project TEXT` - Limit search to specific project

**Examples**:
```bash
cidx scip references UserService              # Find all UserService usages
cidx scip references authenticate --limit 10  # Limit to 10 results
cidx scip references UserService --exact      # Exact match only
```

**When to use**:
- Finding all call sites for a function
- Discovering symbol usage patterns
- Refactoring impact analysis (before renaming/changing API)
- Code review (understanding symbol usage)

---

### 3. Dependencies - What This Symbol Uses

Get symbols that this symbol depends on (outgoing dependencies).

**Usage**:
```bash
cidx scip dependencies SYMBOL [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--depth INTEGER` - Depth of transitive dependencies (default: 1 = direct only)
- `--exact` - Match exact symbol name
- `--project TEXT` - Limit search to specific project

**Examples**:
```bash
cidx scip dependencies UserService              # Direct dependencies only
cidx scip dependencies UserService --depth 2    # Include transitive deps
cidx scip dependencies authenticate --exact     # Exact symbol match
```

**When to use**:
- Understanding what a symbol requires to function
- Analyzing module cohesion
- Identifying circular dependencies
- Planning refactoring (what needs to come along)

---

### 4. Dependents - What Uses This Symbol

Get symbols that depend on this symbol (incoming dependencies).

**Usage**:
```bash
cidx scip dependents SYMBOL [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--depth INTEGER` - Depth of transitive dependents (default: 1 = direct only)
- `--exact` - Match exact symbol name
- `--project TEXT` - Limit search to specific project

**Examples**:
```bash
cidx scip dependents Logger                   # Direct dependents only
cidx scip dependents Logger --depth 2         # Include transitive deps
cidx scip dependents UserService --exact      # Exact symbol match
```

**When to use**:
- Impact analysis before changes
- Understanding symbol reach/importance
- Identifying refactoring scope
- Finding unused code candidates (zero dependents)

---

### 5. Call Chain - Trace Execution Paths

Trace call chains between two symbols (how does A reach B).

**Usage**:
```bash
cidx scip callchain FROM_SYMBOL TO_SYMBOL [OPTIONS]
```

**Options**:
- `--max-depth INTEGER` - Maximum chain length (default 10, max 20)
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--project TEXT` - Filter to specific project path

**Examples**:
```bash
cidx scip callchain main Application.run     # Find paths from main to run
cidx scip callchain Logger UserService       # Trace Logger to UserService
cidx scip callchain A B --max-depth 5        # Limit to 5 hops max
```

**When to use**:
- Debugging execution flow
- Understanding how feature X triggers Y
- Validating architectural boundaries
- Security analysis (untrusted input to sensitive function)

---

### 6. Context - Smart Symbol Context

Get curated file list with relevance scores optimized for understanding a symbol.

**Usage**:
```bash
cidx scip context SYMBOL [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--min-score FLOAT` - Minimum relevance score (0.0-1.0)
- `--project TEXT` - Filter to specific project path

**Examples**:
```bash
cidx scip context UserService              # Get context for UserService
cidx scip context Logger --limit 10        # Limit to top 10 files
cidx scip context Config --min-score 0.5   # Filter low relevance
```

**When to use**:
- AI agents gathering context for code generation
- Onboarding (understanding a subsystem)
- Code review (getting full picture)
- Refactoring preparation (what to read first)

**Output**: Prioritized file list combining definition, references, and dependencies with relevance scoring.

---

### 7. Impact - Change Impact Analysis

Analyze impact of changes to a symbol (full transitive dependent analysis).

**Usage**:
```bash
cidx scip impact SYMBOL [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum results (0 = unlimited)
- `--depth INTEGER` - Analysis depth (default 3, max 10)
- `--project TEXT` - Filter to specific project path
- `--exclude TEXT` - Exclude pattern (e.g., `*/tests/*`)
- `--include TEXT` - Include pattern
- `--kind TEXT` - Filter by symbol kind (class/function/variable)

**Examples**:
```bash
cidx scip impact UserService                  # Full impact analysis
cidx scip impact authenticate --depth 1       # Direct dependents only
cidx scip impact Logger --exclude '*/tests/*' # Exclude test files
cidx scip impact Config --project backend/    # Limit to backend project
```

**When to use**:
- Pre-change risk assessment
- Estimating refactoring effort
- Test planning (what needs testing after change)
- Breaking change analysis for API modifications

---

## Index Management Commands

### 8. Generate - Create SCIP Indexes

Generate SCIP indexes for all discovered projects.

**Usage**:
```bash
cidx scip generate [OPTIONS]
```

**Options**:
- `--project TEXT` - Generate only for specific project path
- `--skip-verify` - Skip automatic verification (for CI performance)

**Examples**:
```bash
cidx scip generate                    # Generate for all projects with verification
cidx scip generate --project backend  # Generate only for backend/
cidx scip generate --skip-verify      # Skip verification for CI performance
```

**Supported project types**:
- Java: Maven projects (pom.xml)
- TypeScript: npm/yarn projects (package.json)
- Python: Poetry projects (pyproject.toml)
- Kotlin: Gradle projects (build.gradle.kts)

**Storage**: Indexes stored in `.code-indexer/scip/`, status in `.code-indexer/scip/status.json`

---

### 9. Status - Check Generation Status

Show SCIP generation status for all projects.

**Usage**:
```bash
cidx scip status [OPTIONS]
```

**Options**:
- `-v, --verbose` - Show detailed per-project status including errors

**Examples**:
```bash
cidx scip status           # Show summary
cidx scip status -v        # Show detailed per-project status
```

**Status states**:
- SUCCESS - All projects successfully generated
- LIMBO - Some succeeded, some failed (partial success)
- FAILED - All projects failed to generate
- PENDING - No generation attempted yet

---

### 10. Rebuild - Regenerate Specific Projects

Rebuild SCIP indexes for specific projects without full regeneration.

**Usage**:
```bash
cidx scip rebuild [PROJECTS...] [OPTIONS]
```

**Options**:
- `--failed` - Rebuild all previously failed projects
- `--force` - Force rebuild even if project already succeeded

**Examples**:
```bash
cidx scip rebuild backend/                 # Rebuild single project
cidx scip rebuild backend/ frontend/       # Rebuild multiple projects
cidx scip rebuild --failed                 # Rebuild all failed projects
cidx scip rebuild --force frontend/        # Force rebuild successful project
```

**When to use**:
- Retrying failed projects after fixing issues
- Updating specific project indexes after code changes
- Recovering from partial generation failures

---

### 11. Verify - Database Integrity Check

Verify SCIP database integrity against source protobuf.

**Usage**:
```bash
cidx scip verify DATABASE_PATH
```

**Examples**:
```bash
cidx scip verify .code-indexer/scip/index.scip.db
cidx scip verify path/to/project.scip.db
```

**Verification checks**:
- Symbol count and content (100 random samples)
- Occurrence count and content (1000 random samples)
- Document paths and languages (100% verification)
- Call graph FK integrity (100% + 100 random edge samples)

**Exit codes**:
- 0 - All verification checks passed
- 1 - One or more verification checks failed

---

## Workflow Examples

### Refactoring Workflow

```bash
# 1. Understand what symbol does
cidx scip definition UserService

# 2. Find all usage locations
cidx scip references UserService

# 3. Assess change impact
cidx scip impact UserService --depth 2

# 4. Get full context for refactoring
cidx scip context UserService --limit 20
```

### Debugging Workflow

```bash
# 1. Find where error handler is defined
cidx scip definition handleError

# 2. Trace how main() reaches handleError
cidx scip callchain main handleError

# 3. Find all error handler call sites
cidx scip references handleError
```

### Dependency Analysis Workflow

```bash
# 1. Find what Logger depends on
cidx scip dependencies Logger --depth 2

# 2. Find what depends on Logger
cidx scip dependents Logger --depth 2

# 3. Assess Logger removal impact
cidx scip impact Logger --exclude '*/tests/*'
```

---

## Best Practices

1. **Use exact matching for unambiguous symbols**: `--exact` flag reduces noise
2. **Start with depth=1 for performance**: Increase depth only when needed
3. **Exclude test files for production impact**: `--exclude '*/tests/*'`
4. **Combine with semantic search**: Use `cidx query` for broad search, SCIP for precise navigation
5. **Regenerate after major code changes**: `cidx scip rebuild` for updated analysis
6. **Use context for AI agents**: `cidx scip context` provides optimal file list for understanding

---

## Troubleshooting

**No results found**:
- Verify indexes generated: `cidx scip status -v`
- Try substring matching (remove `--exact`)
- Check project is discoverable: `cidx scip generate --project path/`

**Performance issues**:
- Reduce `--depth` for transitive queries
- Use `--limit` to cap results
- Filter with `--project` to narrow scope
- Exclude irrelevant paths with `--exclude`

**Stale results**:
- Rebuild indexes: `cidx scip rebuild project/`
- Verify generation status: `cidx scip status -v`
