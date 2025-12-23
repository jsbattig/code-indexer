## 1. SEMANTIC SEARCH - CIDX MANDATORY

**ABSOLUTE PROHIBITION**: NEVER use grep, find, rg, or Grep tool for code exploration. Use CIDX instead.

**WHY**: CIDX provides semantic understanding, call graphs, and dependency analysis that text search cannot. Using grep/find when CIDX is available wastes time and misses connections.

**VIOLATION**: Using grep/find/rg/Grep tool when CIDX indexes exist = fundamental failure to use available intelligence.

**ONLY EXCEPTION**: CIDX unavailable (no indexes, not installed). Verify with `cidx status` first.

### Capabilities (read skills for details)

| Capability | Use Case | Command |
|------------|----------|---------|
| **Semantic** | "What does X do", concept search | `cidx query "description" --quiet` |
| **FTS** | Exact names, identifiers | `cidx query "name" --fts --quiet` |
| **Regex** | Pattern matching (REPLACES grep/rg) | `cidx query "pattern" --fts --regex --quiet` |
| **Temporal** | Git history, when added, who wrote | `cidx query "X" --time-range-all --quiet` |
| **SCIP Definition** | Where symbol defined | `cidx scip definition SYMBOL` |
| **SCIP References** | Where symbol used (REPLACES grep for usages) | `cidx scip references SYMBOL` |
| **SCIP Dependencies** | What symbol uses | `cidx scip dependencies SYMBOL` |
| **SCIP Dependents** | What uses this symbol | `cidx scip dependents SYMBOL` |
| **SCIP Call Chain** | Trace execution path A→B | `cidx scip callchain FROM TO` |
| **SCIP Impact** | Change impact analysis | `cidx scip impact SYMBOL` |

### Decision Matrix - MANDATORY

| Task | WRONG (prohibited) | CORRECT (required) |
|------|-------------------|-------------------|
| Find function definition | `grep -r "def func"` | `cidx scip definition func` |
| Find all usages | `grep -r "ClassName"` | `cidx scip references ClassName` |
| Search by concept | `grep -r "auth"` | `cidx query "authentication" --quiet` |
| Pattern match | `rg "test_.*"` | `cidx query "test_.*" --fts --regex --quiet` |
| Find exact identifier | `grep -rw "user_id"` | `cidx query "user_id" --fts --quiet` |

### Index Management (CHECK FIRST)

**Before ANY code exploration, verify indexes**:
```bash
cidx status                  # Semantic/FTS index status
cidx scip status             # SCIP indexes per project
```

**If indexes missing, create them**:
```bash
cidx init && cidx index      # Semantic + FTS
cidx scip generate           # SCIP call graphs
```

**Supported SCIP languages**: Java, TypeScript, Python, Kotlin, C#, Go

### Key Flags

`--limit N` (start 5-10) | `--language X` | `--path-filter */pattern/*` | `--quiet` (ALWAYS)

### Full Documentation

**Read skills for comprehensive instructions**:
- `~/.claude/skills/cidx/SKILL.md` - Complete reference
- `~/.claude/skills/cidx/reference/scip-intelligence.md` - Call graph/dependency analysis

