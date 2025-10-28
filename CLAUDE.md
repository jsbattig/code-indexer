- When using cidx (code-indexer), the flow to use it is init command must have been run, at least once, on a fresh folder before you can do start. After start is succesful, then you can operate in that space with query command.

- ⚠️ CRITICAL PERFORMANCE PROHIBITION: NEVER add artificial time.sleep() delays to production code to make status changes "visible" to users. This destroys performance (adding minutes of delay across hundreds of files). Fix DISPLAY LOGIC or REFRESH RATE, not processing logic. Adding sleep() to production code for UI visibility is STRICTLY FORBIDDEN.

- When I give a list of e2e, functional, integration, long running tests to troubleshoot and fix, keep in mind that tests don't leave a clean state at the end to improve running performance. Tests should be aware of noisy neighbors and have comprehensive setup that ensure conditions are adjusted to execute tests successfully.

- When I ask you to "lint" you will run the ./lint.sh file and address all and every error reported in a systematic way

- When bumping the version label, you need to always update the readme installs instructions to the command to install matches the latest version
- If you are troubleshooting docker-related issues that appear to be related to security, DON'T try modifying dockerfiles by adding user setup to the dockerfiles. You will make things worse and confuse the troubleshooting process. The files are fine without user setup. Look somewhere else.
- When working on modifying the behavior of a well documented function or if adding a new user-accesible function or --setting to the application you will always read and update the readme file, and you will make sure the --help command reflects the true state of the behavior and functionality of the application
- Don't use fallbacks to using Claude CLI in this project. If you find an issue, you research using your web search tools, and you propose a solution. Claude CLI must be used always when using the "claude" tool within this project. Claude CLI has full access to the disk, and all its files, which is the entire point of the "claude" function. Any fallback is mooth, makes no sense, it's a waste of time and money. Don't go ever, don't even propose a "fallback". A fallback in this context is simply cheating, and we don't want cheating.

- ⚠️ CRITICAL PROGRESS REPORTING: The CLI progress bar behavior is EXTREMELY DELICATE and depends on this exact pattern:
  - SETUP MESSAGES (ℹ️ scrolling): `progress_callback(0, 0, Path(""), info="Setup message")` - total=0 triggers ℹ️ display
  - FILE PROGRESS (progress bar): `progress_callback(current, total_files, file_path, info="X/Y files (%) | emb/s | threads | filename")` - total>0 triggers progress bar, info MUST follow format
  - DO NOT CHANGE without understanding cli.py progress_callback logic
  - Files with progress calls: BranchAwareIndexer, SmartIndexer, HighThroughputProcessor

- If you encounter JSON serialization errors: 1) Use _validate_and_debug_prompt() to analyze, 2) Check for non-ASCII chars/long lines/unescaped quotes, 3) Test with minimal Claude options first. Claude CLI integration uses subprocess calls to avoid JSON serialization issues. Always start with minimal working configuration.

- When I ask you to lint, or when you decide on my own that you need to lint, always run ruff, black and mypy. We will refer to all as "linting".
- When I tell you about failed tests in the context of full-automation.sh, it's so you know, you are not supposed to run that script from your Claude context, they are too slow. You are going to research why they may fail in that context, run them individually to troubleshoot. Eventually, when ready, ask the user to run the full-automation.sh himself/herself
- For end to end test, integration tests, long running tests that rely on real services: don't stop/uninstall services, but ensure prerequisites are met on test setup. Leave services running at end, but ensure conditions are properly set for test to run. Tests can re-init with proper params, cleanup collections, call "start" if necessary. We're doing this to accelerate test execution.
- Ensure that slow, e2e, integration and any code that rely on Voyage AI API don't bleed into github actions and fast-automation.sh scripts. Those are supposed to be fast tests. All tests are discovered and run on full-automation.sh
- Every time you finish implementing a significant new feature or change, you will execute the lint.sh application, AND you will perform a comprehensive documentation check, the README.md file and the help, against what's implemented in the codebase. You will correct any errors, and you will do a second run after that.
- When working on improvements for the smart indexer, always consider the --reconcile function (non git-aware) and ensure consistency across both indexing processes. Treat the --reconcile aspect as equally important, maintaining feature parity and functionality, except for semantically specific module considerations.

## Test Suite Architecture

**fast-automation.sh**: 865+ tests, ~2.5min, local unit tests with full permissions
**GitHub Actions CI**: ~814 tests, ~2min/Python version, restricted environment (no Docker/system writes)
**full-automation.sh**: All tests including E2E/integration, 10+ min, complete validation

**GitHub Actions Exclusions**: Permission-dependent tests excluded via `--ignore=` in workflow:
- Port registry tests (require `/var/lib/code-indexer/` write access)
- VoyageAI integration tests (require API credentials)
- Container-dependent tests (no Docker daemon access)

**Failure Triage**:
- Code issues → fix immediately
- Permission issues → exclude from CI via `--ignore=path/to/test.py` in `.github/workflows/main.yml`
- Environment issues → local-only

**Differential Testing Strategy**:
- GitHub Actions = Subset of tests that work in restricted environments
- fast-automation.sh = Full unit test coverage for local development
- full-automation.sh = Complete testing including integration/E2E

**VoyageAI Integration Tests**: Tests using real VoyageAI API calls are integration tests and should not run in GitHub Actions without API credentials. They remain in fast-automation.sh for local development where API keys are available.

## Full-Automation.sh Python Compatibility

**CRITICAL**: Use `python3 -m pip install` (not bare `pip`) with `--break-system-packages` flag.

**Rationale**: Many Linux distros lack `python` command; externally-managed environments require flag.

**Commands**: Lines 92, 326 use `python3 -m pip install -e ".[dev]" --break-system-packages`
**Tests**: `test_full_automation_python_commands.py`, `test_pip_command_issues.py`

**When adding new pip commands to full-automation.sh**:
1. ALWAYS use `python3 -m pip install` (never bare `pip install`)
2. ALWAYS include `--break-system-packages` flag
3. Test on systems where only `python3` is available

- NEVER, EVER, remove functionality related to our enhanced processing of git projects. The git-awareness aspects, how we optimize processing branches, and keeping track of relationships, deduplication of indexing is what make this project unique. If you ever go into a refactoring rabbit hole and you will start removing functionality that enables this capability you must stop, immediately, and ask if that's the true intent of the work you been asked to do.
- When working on fixing quick feedback unit tests, or fast tests, always use ./fast-automation.sh. This shell file is specifically tuned to run tests that run fast, so they can be run efficiently from within Claude Code as a first layer of protection ensuring our tests pass and we didn't introduce regressions.
- When indexing, progress reporting is done real-time, in a single line at the bottom, showing a progress bar, and right next to it we show speed metrics and current file being processed. Don't change this approach without confirmation from the user. This is how it is, and it should be for all indexing operations, we don't show feedback scrolling the console, EVER, NEVER, EVER. Ask for confirmation if you are about to change this behavior.
- When asking to bump version, you will always check readme in case there's references to the version number, and you will always update the release notes files with the latest changes
- In the context of this project, we don't use the /tmp folder as a temporary location. We use ~/.tmp
- The ports configuration in this project is "local", not "global". The local configuration is found walking folder structure upwards, like git does, and when we find our configuration file, that dictates everything, including ports of ALL our containers. There's no shared containers among multiple projects, and a project is defined as a location in the disk and all its subfolders where a config file can be found. Containers are bound to a root folder that has a config file. Period. The code should NEVER, EVER, use "default ports". Ports are ALWAYS dynamically calculated based on the project.
- When working on this project, it's absolutely critical to remember that we support both podman and docker. Development and most testing is done with podman, but there are docker-specific tests to verify no regressions occur. Docker usage is achieved in Docky Linux using the --force-docker flag.
- Our solution uses a per-project configuration and container set. Tests need to be aware of this. Many tests written before this big refactoring, were written with implied and hard-coded port numbers, they didn't reuse folders, making them inefficient and slow, some will start/stop containers manually, some e2e tests will tinker with internal calls rather than using the cidx (console) application directly (which is the right way to do it).
- The last step of every development engagement to implement a feature is to run fast-automation.sh. Only when it passes in full, we consider the task done.

- **🚨 VOYAGEAI BATCH PROCESSING TOKEN LIMITS**: VoyageAI API enforces 120,000 token limit per batch request. The VoyageAI client now implements token-aware batching that automatically splits large file batches to respect this limit while maintaining performance optimization. Files with >100K estimated tokens will be processed in multiple batches transparently. Error "max allowed tokens per submitted batch is 120000" indicates this protection is working correctly.

## Embedding Provider Strategy

**PRODUCTION PROVIDER**: VoyageAI is the ONLY production embedding provider. It provides high-quality embeddings via API with acceptable performance and reliability.

**OLLAMA STATUS**: Ollama is EXPERIMENTAL ONLY and NOT for production use. It was tested as a local embedding option but is WAY too slow for practical usage. Ollama remains in the codebase for testing/development purposes only.

**CRITICAL**: When discussing optimizations, architecture, or production deployments, focus exclusively on VoyageAI. Ollama performance and optimization are not priorities since it's not production-viable.

## VoyageAI Token Counting Optimization

**CRITICAL ARCHITECTURE**: We use an embedded tokenizer (`embedded_voyage_tokenizer.py`) instead of the voyageai library for token counting. This was a carefully researched optimization.

**WHY EMBEDDED TOKENIZER**:
- The `voyageai` library was ONLY used for `count_tokens()` (440-630ms import overhead for one function!)
- Token counting is critical for respecting VoyageAI's 120,000 token/batch API limit
- We tried "myriad other ways" to count tokens - all failed
- VoyageAI's official tokenizer was the only accurate method

**IMPLEMENTATION**:
- Extracted minimal tokenization logic from voyageai library
- Uses `tokenizers` library directly (loads official VoyageAI models from HuggingFace)
- Lazy imports - only loads when actually counting tokens
- Caches tokenizers per model for blazing fast performance (0.03ms)
- Provides 100% identical token counts to `voyageai.Client.count_tokens()`

**ACCURACY GUARANTEE**: All 9 test cases (Unicode, emojis, code, SQL, edge cases) match voyageai library exactly. This is production-ready and maintains critical accuracy for API token limits.

**PERFORMANCE**: Eliminated 440-630ms import overhead. See `OPTIMIZATION_SUMMARY.md` for detailed analysis.

**DO NOT**: Remove or replace the embedded tokenizer without extensive testing. Token counting accuracy is non-negotiable for VoyageAI API compliance.

## Import Time Optimization Status

**COMPLETED OPTIMIZATIONS**:
1. ✅ **voyageai library eliminated**: 440-630ms → 0ms (100% removal)
2. ✅ **CLI lazy loading implemented**: 736ms → 329ms (55% faster, 407ms saved)

**RESULTS** (see `LAZY_IMPORT_RESULTS.md`):
- `cidx --help`: ~800ms → ~350ms (56% faster)
- `cidx query`: ~1656ms → ~1249ms (25% faster)
- Total combined savings: 847-1037ms (voyageai + lazy loading)

**REMAINING TIME BREAKDOWN** (329ms):
- pydantic (config validation): ~150ms - unavoidable without removing type safety
- rich (console output): ~80ms - unavoidable without removing formatting
- httpx (HTTP client): ~40ms - core dependency
- Standard library: ~40ms - unavoidable
- cli.py self time: ~9.4ms - minimal

**FUTURE OPPORTUNITIES** (diminishing returns):
- Config lazy loading: ~50-100ms potential
- Rich output optimization: ~30-50ms potential
- HNSW index preloading: ~200-300ms potential (runtime, not startup)
- Daemon mode: ~1000+ms potential (requires IPC architecture)

**CONCLUSION**: Current 329ms startup is acceptable. Further optimization requires aggressive changes with questionable ROI.

## CIDX Repository Lifecycle Architecture

**CRITICAL UNDERSTANDING**: The CIDX system operates on a **Golden Repository → Activated Repository → Container Lifecycle** architecture.

### Complete Repository Lifecycle Workflow

**Phase 1 - Golden Repository** (`~/.cidx-server/data/golden-repos/<alias>/`):
- Clone → `cidx init` → `cidx start` → `cidx index` → `cidx stop`
- Result: Complete Qdrant index, stopped containers, ready for activation
- For local repos: Regular copy (NOT CoW) to avoid cross-device link issues
- For remote repos: `git clone --depth=1` for efficiency

**Phase 2 - Activation** (`~/.cidx-server/data/activated-repos/<user>/<alias>/`):
- CoW clone (`git clone --local`) shares index data via hardlinks
- User-specific workspace, no re-indexing required
- Branch setup: Configures origin remote pointing to golden repository

**Phase 3 - Query-Time Containers**:
- Containers run in ACTIVATED repos (not golden)
- Per-repo config: `ConfigManager.create_with_backtrack(repo_path)`
- Auto-start on first query, unique ports per project
- Port calculation: `GlobalPortRegistry._calculate_project_hash()`

### Container Architecture

**Naming Convention**: `cidx-{project_hash}-{service}` (qdrant, data-cleaner) - Note: ollama containers exist but are experimental only
**Port Allocation**: Dynamic calculation per activated repo, stored in `.code-indexer/config.json`
**State Management**: Startup on first query, health monitoring, auto-recovery, manual shutdown via `cidx stop`

**Port Sync**: Container startup, health checks (`DockerManager._get_service_url()`), query ops all use same project config

### Query Execution Flow

1. User makes semantic search request
2. Repository resolution: Find activated repository path
3. Configuration loading: Load repo-specific config with ports
4. Container check: QdrantClient detects if containers running
5. Auto-start: If containers stopped, automatically start them
6. Vector search: Execute semantic search with real embeddings
7. Results return: Format and return search results

### Key Implementation Details

**SemanticSearchService Integration**:
```python
# CORRECT: Repository-specific configuration loading
config_manager = ConfigManager.create_with_backtrack(Path(repo_path))
config = config_manager.get_config()

# CORRECT: Repository-specific Qdrant client (auto-starts containers)
qdrant_client = QdrantClient(config=config.qdrant, project_root=Path(repo_path))

# CORRECT: Repository-specific embedding service
embedding_service = EmbeddingProviderFactory.create(config=config)
```

**Configuration Hierarchy**:
1. Repository Config: `.code-indexer/config.json` (project-specific ports, embedding provider)
2. Global Config: `~/.cidx-server/config.yaml` (server-wide settings)
3. Runtime Config: Dynamic port allocation and container state

### Common Architectural Misconceptions

❌ Containers run in golden repositories | Ports are hardcoded | Index data duplicated | Containers manually started | One container set serves all repos
✅ Containers in activated repos | Dynamic ports per project | CoW-shared index data | Auto-start on query | Each activated repo has own container set

This architecture provides scalable, multi-user semantic code search with efficient resource utilization and proper isolation between users while sharing expensive index computation through CoW cloning.

## SEMANTIC SEARCH - MANDATORY FIRST ACTION

**CIDX FIRST**: Always use `cidx query` before grep/find/rg for semantic searches.

**Decision Rule**:
- "What code does", "Do we support", "Where is X implemented" → CIDX
- Exact text (variable names, config values, log messages) → grep/find

**Key Parameters**: `--limit N` (results, default 10) | `--language python` (filter by language) | `--path-filter */tests/*` (filter by path pattern) | `--min-score 0.8` (similarity threshold) | `--accuracy high` (higher precision) | `--quiet` (minimal output)

**Examples**: `cidx query "authentication login" --quiet` | `cidx query "error handling" --language python --limit 20` | `cidx query "database connection" --path-filter */services/* --min-score 0.8`

**Fallback**: Use grep/find only when cidx unavailable or for exact string matches.

**When to Use**:
✅ "Where is X implemented?" → `cidx query "X implementation" --quiet`
✅ Concept/pattern discovery → Semantic search finds related code
✅ "How does Y work?" → `cidx query "Y functionality" --quiet`
❌ Exact string matches (var names, config values) → Use grep/find
❌ General concepts you can answer directly → No search needed

**Supported Languages**: python, javascript, typescript, java, go, rust, cpp, c, php, swift, kotlin, shell, sql, yaml

**Score Interpretation**: 0.9-1.0 (exact match) | 0.7-0.8 (very relevant) | 0.5-0.6 (moderate) | <0.3 (noise)

**Search Best Practices**:
- Use natural language queries matching developer intent
- Try multiple search terms if first search doesn't yield results
- Search for both implementation AND usage patterns
- Use specific technical terms from domain/framework

**Query Effectiveness Examples**:
- Instead of: "authentication" → Try: "login user authentication", "auth middleware", "token validation"

**Filtering Strategies**:
- `--language python --quiet` - Focus on specific language
- `--path "*/tests/*" --quiet` - Find test patterns
- `--min-score 0.8 --quiet` - High-confidence matches only
- `--limit 20 --quiet` - Broader exploration
- `--accuracy high --quiet` - Maximum precision for complex queries

**Practical Examples** (ALWAYS USE --quiet):
- Concept: `cidx query "authentication mechanisms" --quiet`
- Implementation: `cidx query "API endpoint handlers" --language python --quiet`
- Testing: `cidx query "unit test examples" --path-filter "*/tests/*" --quiet`
- Multi-step: Broad `cidx query "user management" --quiet` → Narrow `cidx query "user authentication" --min-score 0.8 --quiet`

**Semantic vs Text Search Comparison**:
✅ `cidx query "user authentication" --quiet` → Finds login, auth, security, credentials, sessions
❌ `grep "auth"` → Only finds literal "auth" text, misses related concepts

## CIDX Server Architecture - Internal Operations Only

**CRITICAL ARCHITECTURAL PRINCIPLE**: The CIDX server contains ALL indexing functionality internally and should NEVER call external `cidx` commands via subprocess.

**Key Insights**:
- **Server IS the CIDX application** - Direct access to all indexing code (FileChunkingManager, ConfigManager, etc.)
- **No external subprocess calls** except git operations (git pull, git status, etc.)
- **Internal API calls only** - Use existing services like `FileChunkingManager.index_repository()` directly
- **Configuration integration** - Use `ConfigManager.create_with_backtrack()` for repository-specific config

**WRONG Pattern** (External subprocess):
```python
# WRONG - Don't do this in server code
subprocess.run(["cidx", "index"], cwd=repo_path)
```

**CORRECT Pattern** (Internal API):
```python
# CORRECT - Use internal services directly
from ...services.file_chunking_manager import FileChunkingManager
from ...config import ConfigManager

config_manager = ConfigManager.create_with_backtrack(repo_path)
chunking_manager = FileChunkingManager(config_manager)
chunking_manager.index_repository(repo_path=str(repo_path), force_reindex=False)
```

**Why This Matters**: Performance (no process overhead), error handling (proper exception catching), progress reporting (direct callbacks), configuration (same context), architecture (components work together).

**Application**: This applies to ALL server operations including sync jobs, background processing, and API endpoints.

## Critical Test Execution Timeout Requirements

**MANDATORY 20-MINUTE TIMEOUT**: When running automation test scripts, ALWAYS use 1200000ms (20 minute) timeout to prevent premature termination.

**Timeout Knowledge**:
- fast-automation.sh: ~8-10 minutes execution, requires 20-minute timeout for safety
- server-fast-automation.sh: ~8 minutes execution, requires 20-minute timeout for safety
- full-automation.sh: 10+ minutes execution, requires 20-minute timeout minimum
- Default 2-minute timeout: Will cause premature failure and incomplete test results

**CRITICAL**: Premature timeout termination prevents proper identification of failing tests and leads to incomplete debugging information. Always use full 20-minute timeout when running these scripts to get complete test results and proper failure analysis.

## Mandatory GitHub Actions Monitoring Workflow

**CRITICAL REQUIREMENT**: Every time code is pushed to GitHub, you MUST automatically monitor the GitHub Actions workflow and troubleshoot until a clean run is achieved.

**Workflow**: `git push` → `gh run list --limit 5` → If failed: `gh run view <run-id> --log-failed` → Fix → Repeat

**Failure Categories**:
- **Linting** (F841 unused vars, F401 unused imports): Fix via `ruff check --fix src/ tests/`
- **Permissions** (Docker/API/filesystem): Add `--ignore=path/to/test.py` to `.github/workflows/main.yml`
- **Code Issues** (imports/types/logic): Fix root cause

**Common Commands**:
```bash
gh run list --limit 5                    # Check recent runs
gh run view <run-id> --log-failed        # Get detailed failure logs
ruff check --fix src/ tests/             # Auto-fix linting issues
```

**Zero Tolerance**: Never leave GitHub Actions in failed state. Fix failures within same development session. Ensure clean runs before considering work complete.

**Typical Issues**: New test files with unused imports from template copying | Integration tests requiring CI exclusion | Variable assignments for potential future use | Import dependencies not used in test scenarios.