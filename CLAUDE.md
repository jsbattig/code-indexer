# Code-Indexer (CIDX) Project Instructions

## 1. Operational Modes Overview

CIDX has **three operational modes**. Understanding which mode you're working in is critical.

### Mode 1: CLI Mode (Direct, Local)

**What**: Direct command-line tool for local semantic code search
**Storage**: FilesystemVectorStore in `.code-indexer/index/` (container-free)
**Use Case**: Individual developers, single-user workflows
**Commands**: `cidx init`, `cidx index`, `cidx query`

**Characteristics**:
- Indexes code locally in project directory
- No daemon, no server, no network
- Vectors stored as JSON files on filesystem
- Each query loads indexes from disk

### Mode 2: Daemon Mode (Local, Cached)

**What**: Local RPyC-based background service for faster queries
**Storage**: Same FilesystemVectorStore + in-memory cache
**Use Case**: Developers wanting faster repeated queries and watch mode
**Commands**: `cidx config --daemon`, `cidx start`, `cidx watch`

**Characteristics**:
- Caches HNSW/FTS indexes in memory (daemon process)
- Auto-starts on first query when enabled
- Unix socket communication (`.code-indexer/daemon.sock`)
- Faster queries (~5ms cached vs ~1s from disk)
- Watch mode for real-time file change indexing

### Mode 3: Server Mode (Multi-User, Team)

**What**: FastAPI-based team server for multi-user semantic search
**Storage**: Golden Repos (shared) + Activated Repos (per-user CoW clones)
**Use Case**: Team collaboration, centralized code search
**Commands**: Server runs separately, CLI uses `--remote` flag

**Characteristics**:
- **Golden Repositories**: Shared source repos indexed once (`~/.cidx-server/data/golden-repos/`)
- **Activated Repositories**: User-specific workspaces via CoW cloning (`~/.cidx-server/data/activated-repos/<user>/`)
- REST API with JWT authentication
- Background job system for indexing/sync
- Multi-user access control

**IMPORTANT**: Golden/Activated repos are SERVER MODE ONLY. CLI and Daemon modes don't use these concepts.

---

## 2. Architecture Details

**For Full Details**: See `/docs/v5.0.0-architecture-summary.md` and `/docs/v7.2.0-architecture-incremental-updates.md`

### Vector Storage (All Modes)

**Current Architecture**: **FilesystemVectorStore** - Container-free, filesystem-based

**Key Points**:
- Vectors as JSON files in `.code-indexer/index/{collection}/`
- Quantization: Model dims (1024/1536/768) → 64-dim → 2-bit → filesystem path
- Git-aware: Blob hashes (clean files), text content (dirty files)
- Performance: <1s query, <20ms incremental HNSW updates
- Thread-safe with atomic writes
- Supports multiple embedding dimensions (VoyageAI: 1024/1536, Ollama: 768)

**Backend Options**:
- **FilesystemBackend** (Production, Default): No containers, instant
- **QdrantContainerBackend** (Legacy, Deprecated): Backward compatibility only

### Key Architecture Topics (See Docs)

**From `/docs/v5.0.0-architecture-summary.md`**:
- Client-Server architecture (Server Mode)
- Golden/Activated repository system (Server Mode)
- Authentication & security (JWT, rate limiting)
- Background job system (Server Mode)
- Git sync integration (Server Mode)

**From `/docs/v7.2.0-architecture-incremental-updates.md`**:
- Incremental HNSW updates (All Modes)
- Change tracking system
- Real-time vs batch updates
- Performance optimizations

---

## 3. Daily Development Workflows

### Test Suites

- **fast-automation.sh**: 865+ tests, ~2.5min - Run from Claude, MUST stay fast
- **server-fast-automation.sh**: Server-specific tests
- **GitHub Actions CI**: ~814 tests, restricted environment
- **full-automation.sh**: Complete suite, 10+ min - Ask user to run

**Critical**: Use **1200000ms (20 min) timeout** when running automation scripts

**Testing Principles**:
- Tests don't clean state (performance optimization)
- NO container start/stop (filesystem backend is instant)
- E2E tests use `cidx` CLI directly
- Slow tests excluded from fast suites

**Definition of Done**: Feature complete when fast-automation.sh passes fully

### Test Performance Management (MANDATORY)

**ABSOLUTE PROHIBITION**: NEVER introduce slow-running tests to fast-automation.sh without explicit justification.

**Performance Standards**:
- **Individual test target**: <5 seconds per test
- **Suite total target**: <3 minutes for 865+ tests
- **Action threshold**: Any test >10 seconds requires investigation
- **Exclusion threshold**: Tests >30 seconds move to full-automation.sh

**Timing Telemetry (MANDATORY)**:

Every fast-automation.sh execution MUST collect and analyze timing data:

```bash
# Run with timing telemetry
pytest tests/ --durations=20 --tb=short -v

# Or use pytest-benchmark for detailed metrics
pytest tests/ --benchmark-only --benchmark-autosave
```

**Post-Execution Analysis Workflow**:
1. Review `--durations=20` output (20 slowest tests)
2. Identify any tests >5 seconds
3. For slow tests, determine root cause:
   - Unnecessary I/O operations
   - Missing test fixtures/caching
   - Inefficient setup/teardown
   - Actual feature complexity (inherent slowness)
4. Take action based on cause:
   - **Fixable**: Optimize the test (cache fixtures, reduce I/O, parallelize)
   - **Inherent slowness**: Move to full-automation.sh ignore list
   - **Borderline**: Add `@pytest.mark.slow` decorator for conditional execution

**Slow Test Ignore List**:

Maintain explicit ignore list in `pytest.ini` or `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselected by fast-automation.sh)",
    "integration: marks integration tests (may be slow)",
]
```

**fast-automation.sh MUST exclude slow tests**:
```bash
pytest tests/ -m "not slow" --durations=20
```

**Monitoring Commands**:
```bash
# Identify slow tests
pytest tests/ --durations=0 | grep "s call" | sort -rn -k1

# Benchmark specific test
pytest tests/path/to/test.py::test_name --durations=0 -v

# Profile test execution
pytest tests/ --profile --profile-svg
```

**When Adding New Tests**:
1. Run test individually with `--durations=0`
2. If >5 seconds, investigate optimization opportunities FIRST
3. If inherently slow (>30s), mark with `@pytest.mark.slow` and add to full-automation.sh
4. Document why test is slow in test docstring
5. Verify fast-automation.sh total time doesn't exceed 3 minutes

**Red Flags Requiring Immediate Investigation**:
- fast-automation.sh exceeds 3 minutes total
- Any single test exceeds 10 seconds
- Test duration increases >20% without feature changes
- Timing variance >50% between runs (flaky performance)

### Linting & Quality

**Linting**: Run `./lint.sh` (ruff, black, mypy) after significant changes

**GitHub Actions Monitoring** (MANDATORY):
```bash
git push
gh run list --limit 5
gh run view <run-id> --log-failed  # If failed
ruff check --fix src/ tests/        # Fix linting
```

**Zero Tolerance**: Never leave GitHub Actions in failed state. Fix within same session.

### Python Compatibility

**CRITICAL**: Always use `python3 -m pip install --break-system-packages` (never bare `pip`)

### Documentation Updates

**After Feature Implementation**:
1. Run `./lint.sh`
2. Verify README.md accuracy
3. Verify `--help` matches implementation
4. Fix errors, second verification run

**Version Bumps**: Update README install instructions, release notes, all version references

---

## 4. Critical Rules (NEVER BREAK)

### Performance Prohibitions

⚠️ **NEVER add `time.sleep()` to production code** for UI visibility. Fix display logic, not processing logic.

### Progress Reporting (EXTREMELY DELICATE)

**Pattern**:
- Setup: `progress_callback(0, 0, Path(""), info="Setup")` → ℹ️ scrolling
- Progress: `progress_callback(current, total, file, info="X/Y files...")` → progress bar

**Rules**:
- Single line at bottom with progress bar + metrics
- NO scrolling console feedback EVER
- DO NOT CHANGE without understanding `cli.py` progress_callback
- Ask confirmation before ANY changes
- Files with progress: BranchAwareIndexer, SmartIndexer, HighThroughputProcessor

### Git-Awareness (CORE FEATURE)

**NEVER remove** these capabilities:
- Git-awareness aspects
- Branch processing optimization
- Relationship tracking
- Deduplication of indexing

This makes CIDX unique. If refactoring removes this, **STOP IMMEDIATELY**.

### Smart Indexer Consistency

When working on smart indexer, always consider `--reconcile` (non git-aware) and maintain feature parity.

### Configuration

- **Temporary Files**: Use `~/.tmp` (NOT `/tmp`)
- **Ports** (Legacy Qdrant only): Dynamic per-project, NEVER hardcoded
- **Containers** (Legacy): Support podman/docker for backward compatibility only

---

## 5. Performance & Optimization

### FTS Lazy Import (CRITICAL)

⚠️ **NEVER import Tantivy/FTS at module level** in files imported during CLI startup

**Correct Pattern**:
```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tantivy_index_manager import TantivyIndexManager

# Inside method where FTS used:
if enable_fts:
    from .tantivy_index_manager import TantivyIndexManager
    fts_manager = TantivyIndexManager(fts_index_dir)
```

**Why**: Keeps `cidx --help` fast (~1.3s vs 2-3s)

**Verify**: `python3 -c "import sys; from src.code_indexer.cli import cli; print('tantivy' in sys.modules)"` → `False`

### Import Optimization Status

**Completed**:
- voyageai library: 440-630ms → 0ms (eliminated)
- CLI lazy loading: 736ms → 329ms

**Current**: 329ms startup (acceptable, further optimization questionable ROI)

---

## 6. Embedding Provider

### VoyageAI (PRODUCTION ONLY)

**ONLY production provider** - Focus EXCLUSIVELY on VoyageAI

**Token Counting**:
- Use `embedded_voyage_tokenizer.py`, NOT voyageai library
- Critical for 120,000 token/batch API limit
- Lazy imports, caches per model (0.03ms)
- 100% identical to `voyageai.Client.count_tokens()`
- **DO NOT remove/replace** without extensive testing

**Batch Processing**:
- 120,000 token limit per batch enforced
- Automatic token-aware batching
- Transparent batch splitting

### Ollama (EXPERIMENTAL)

**NOT for production** - Too slow, testing/dev only

---

## 7. CIDX Usage Quick Reference

### CLI Mode (Most Common)

```bash
cidx init                           # Create .code-indexer/
cidx index                          # Index codebase
cidx query "authentication" --quiet # Semantic search
cidx query "def.*" --fts --regex    # FTS/regex search
```

**Key Flags** (ALWAYS use `--quiet`):
- `--limit N` - Results (default 10)
- `--language python` - Filter by language
- `--path-filter */tests/*` - Path pattern
- `--min-score 0.8` - Similarity threshold
- `--accuracy high` - Higher precision
- `--quiet` - Minimal output

**Search Decision**:
- ✅ "What code does", "Where is X implemented" → CIDX
- ❌ Exact strings (variable names, config) → grep/find

### Daemon Mode (Optional, Faster)

```bash
cidx config --daemon      # Enable daemon
cidx start                # Start daemon (auto-starts on first query)
cidx query "..."          # Uses cached indexes
cidx watch                # Real-time indexing
cidx watch-stop           # Stop watch
cidx stop                 # Stop daemon
```

### Server Mode (Team Usage)

See server documentation - involves server setup, user management, golden/activated repos.

---

## 8. Mode-Specific Concepts

### CLI Mode Concepts
- `.code-indexer/` - Project config and index storage
- FilesystemVectorStore - Vector storage
- Direct disk I/O per query

### Daemon Mode Concepts
- RPyC service on Unix socket
- In-memory HNSW/FTS cache
- Watch mode for real-time updates
- `.code-indexer/daemon.sock`

### Server Mode Concepts (ONLY)
- **Golden Repositories** - Shared indexed repos
- **Activated Repositories** - User-specific CoW clones
- REST API with JWT auth
- Background job system
- Multi-user access control

**IMPORTANT**: Don't reference golden/activated repos outside Server Mode context.

---

## 9. Miscellaneous

### Claude CLI Integration

**NO FALLBACKS** - Research and propose solutions, no cheating

**JSON Errors**: Use `_validate_and_debug_prompt()`, check non-ASCII/long lines/quotes

---

## 10. Where to Find More

**Detailed Architecture**: `/docs/v5.0.0-architecture-summary.md`, `/docs/v7.2.0-architecture-incremental-updates.md`

**This File's Purpose**: Day-to-day development essentials and mode-specific context
