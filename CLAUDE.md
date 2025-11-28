# Code-Indexer (CIDX) Project Instructions

## 0. DOCUMENTATION STANDARDS

**NO EMOJI/ICONOGRAPHY**: Never use emoji, unicode icons, or decorative symbols in any documentation files (README.md, CLAUDE.md, CHANGELOG.md, docs/*.md). Use plain text headers and formatting only. This applies to all project documentation.

**Examples of forbidden iconography:**
- Emoji: 🔍 🕰️ ⚡ 🎯 🔄 🤖 ✅ ❌ 👍 🚀 🔧 🔐
- Unicode symbols: ✓ ✗ ★ ● ◆ → ←
- Decorative characters

**Correct heading format**: Use plain text only
```markdown
### Performance Improvements
### Git History Search
```

---

## 1. CRITICAL BUSINESS INSIGHT - Query is Everything

**THE SINGLE MOST IMPORTANT FEATURE**: Query capability is the core value proposition of CIDX. All query features available in CLI MUST be available in MCP/REST APIs with full parity.

**Query Parity is Non-Negotiable**: Any feature gap between CLI and MCP/REST query interfaces represents a critical degradation of the product's primary function. This is not optional - this is the business.

**Current Status** (as of 2025-11-18):
- CLI query parameters: 23 total
- MCP query parameters: 11 total (48% parity)
- **P0 filters implemented**: language, exclude_language, path_filter, exclude_path, file_extensions, accuracy
- **Remaining gap**: FTS-specific options (8 params), temporal options (4 params)

**Never remove or break query functionality** without explicit approval. Query degradation = product failure.

---

## 2. Operational Modes Overview

CIDX has **two operational modes** (simplified from three in v7.x). Understanding which mode you're working in is critical.

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
- Container-free, instant setup

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
- Container-free, runs as local process

---

## 3. Architecture Details

**For Full Details**: See `/docs/v5.0.0-architecture-summary.md` and `/docs/v7.2.0-architecture-incremental-updates.md`

### Vector Storage (All Modes)

**Current Architecture**: **FilesystemVectorStore** - Container-free, filesystem-based (only backend in v8.0+)

**Key Points**:
- Vectors as JSON files in `.code-indexer/index/{collection}/`
- Quantization: Model dims (1024/1536) → 64-dim → 2-bit → filesystem path
- Git-aware: Blob hashes (clean files), text content (dirty files)
- Performance: <1s query, <20ms incremental HNSW updates
- Thread-safe with atomic writes
- Supports VoyageAI embedding dimensions (1024 for voyage-3, 1536 for voyage-3-large)

### Key Architecture Topics (See Docs)

**From `/docs/v7.2.0-architecture-incremental-updates.md`**:
- Incremental HNSW updates (All Modes)
- Change tracking system
- Real-time vs batch updates
- Performance optimizations

**From `/docs/architecture.md`**:
- Filesystem vector storage architecture
- HNSW graph-based indexing
- Git-aware storage strategies
- Query performance optimization

---

## 4. Daily Development Workflows

### Test Suites

- **fast-automation.sh**: 865+ tests, ~6-7min - Run from Claude, MUST stay fast
- **server-fast-automation.sh**: Server-specific tests
- **GitHub Actions CI**: ~814 tests, restricted environment
- **full-automation.sh**: Complete suite, 10+ min - Ask user to run

**Critical**: Use **600000ms (10 min) timeout** for fast-automation.sh, **1200000ms (20 min) timeout** for full-automation.sh

**Testing Principles**:
- Tests don't clean state (performance optimization)
- Container-free architecture (instant setup, no overhead)
- E2E tests use `cidx` CLI directly
- Slow tests excluded from fast suites

**MANDATORY Testing Workflow Order**:

1. **Targeted Unit Tests FIRST**: Write and run specific unit tests for the functionality being added/fixed/modified
2. **Manual Testing SECOND**: Execute manual testing to verify the functionality works end-to-end
3. **fast-automation.sh LAST**: Run full regression suite as FINAL validation before marking work complete

**Why This Order**:
- fast-automation.sh takes 6-7 minutes - too slow for rapid feedback loops
- Targeted unit tests provide immediate feedback (seconds, not minutes)
- Manual testing validates real-world behavior before committing to full suite
- fast-automation.sh is the FINAL gate, not a development tool

**ABSOLUTE PROHIBITION**: NEVER run fast-automation.sh as part of iterative development. Use it ONLY as final validation after unit tests pass and manual testing confirms functionality works.

**Definition of Done**: Feature complete when fast-automation.sh passes fully (after targeted unit tests pass AND manual testing confirms functionality)

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

## 5. Critical Rules (NEVER BREAK)

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
- **Container-free**: No ports, no containers, instant setup

---

## 6. Performance & Optimization

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

## 7. Embedding Provider

### VoyageAI (ONLY PROVIDER)

**ONLY supported provider in v8.0+** - Focus EXCLUSIVELY on VoyageAI

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

**Models**:
- **voyage-3** (default): 1024-dimensional embeddings, best balance of quality and speed
- **voyage-3-large**: 1536-dimensional embeddings, highest quality

---

## 8. CIDX Usage Quick Reference

### CLI Mode (Most Common)

```bash
cidx init                           # Create .code-indexer/
cidx index                          # Index codebase
cidx query "authentication" --quiet # Semantic search
cidx query "def.*" --fts --regex    # FTS/regex search
```

**Key Flags** (ALWAYS use `--quiet`):
- `--limit N` - Results (default 10, start with 5-10 to conserve context window)
- `--language python` - Filter by language
- `--path-filter */tests/*` - Path pattern
- `--min-score 0.8` - Similarity threshold
- `--accuracy high` - Higher precision
- `--quiet` - Minimal output

**Context Conservation**: Start with low `--limit` values (5-10) on initial queries. High limits consume context window rapidly when results contain large code files.

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

---

## 9. Mode-Specific Concepts

### CLI Mode Concepts
- `.code-indexer/` - Project config and index storage
- FilesystemVectorStore - Vector storage
- Direct disk I/O per query
- Container-free, instant setup

### Daemon Mode Concepts
- RPyC service on Unix socket
- In-memory HNSW/FTS cache
- Watch mode for real-time updates
- `.code-indexer/daemon.sock`
- Container-free, runs as local process

---

## 10. Miscellaneous

### Local Testing and Deployment

**Configuration File**: `.local-testing` (gitignored)

Contains sensitive deployment information for test environments:
- CIDX server credentials and deployment process
- Mac laptop credentials and MCPB installation process
- One-liner deployment commands

Consult this file when deploying to test environments.

### Claude CLI Integration

**NO FALLBACKS** - Research and propose solutions, no cheating

**JSON Errors**: Use `_validate_and_debug_prompt()`, check non-ASCII/long lines/quotes

---

## 11. Where to Find More

**Detailed Architecture**: `/docs/v5.0.0-architecture-summary.md`, `/docs/v7.2.0-architecture-incremental-updates.md`

**This File's Purpose**: Day-to-day development essentials and mode-specific context
