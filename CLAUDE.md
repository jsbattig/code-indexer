- When using cidx (code-indexer), the flow to use it is init command must have been run, at least once, on a fresh folder before you can do start. After start is succesful, then you can operate in that space with query command.

- ⚠️ CRITICAL PERFORMANCE PROHIBITION: NEVER add artificial time.sleep() delays to production code to make status changes "visible" to users. This is a brain-dead approach that destroys performance (adding minutes of delay across hundreds of files). If status transitions are too fast to see, fix the DISPLAY LOGIC or REFRESH RATE, not the processing logic. Adding sleep() to production code for UI visibility is STRICTLY FORBIDDEN and demonstrates fundamental misunderstanding of performance engineering.

- When I give a list of e2e, functional, integration, long running tests to troubleshoot and fix, keep in mind that tests don't leave a clean a state at the end to improve running performance, they leave service running and dirty collections. Tests should be aware of this, of noisy neighboor, and have comprehensive setup that ensure conditions are adjusted execute the tests succesfully.

- When I ask you to "lint" you will run the ./lint.sh file and address all and every error reported in a systematic way

- When bumping the version label, you need to always update the readme installs instructions to the command to install matches the latest version
- If you are troubleshooting docker-related issues that appear to be related to security, DON'T try modifying dockerfiles by adding user setup to the dockerfiles. You will make things worse and confuse the troubleshooting process. The files are fine without user setup. Look somewhere else.
- When working on modifying the behavior of a well documented function or if adding a new user-accesible function or --setting to the application you will always read and update the readme file, and you will make sure the --help command reflects the true state of the behavior and functionality of the application
- Don't use fallbacks to using Claude CLI in this project. If you find an issue, you research using your web search tools, and you propose a solution. Claude CLI must be used always when using the "claude" tool within this project. Claude CLI has full access to the disk, and all its files, which is the entire point of the "claude" function. Any fallback is mooth, makes no sense, it's a waste of time and money. Don't go ever, don't even propose a "fallback". A fallback in this context is simply cheating, and we don't want cheating.

- ⚠️  ⚠️  ⚠️  CRITICAL PROGRESS REPORTING WARNING ⚠️  ⚠️  ⚠️  
  The CLI progress bar behavior is EXTREMELY DELICATE and depends on this exact pattern:
  
  ✅ SETUP MESSAGES (show as ℹ️ scrolling):
     progress_callback(0, 0, Path(""), info="Setup message here")
     - total=0 triggers ℹ️ message display in CLI
  
  ✅ FILE PROGRESS (show as progress bar):
     progress_callback(current, total_files, file_path, info="X/Y files (%) | emb/s | threads | filename")
     - total>0 triggers progress bar display in CLI
     - info MUST follow format: "files (%) | emb/s | threads | filename"
  
  ❌ DO NOT CHANGE without understanding the CLI logic in cli.py progress_callback!
  ❌ Breaking this pattern will cause either no progress bar or scrolling spam
  
  Files with progress calls: BranchAwareIndexer, SmartIndexer, HighThroughputProcessor
- If you encounter JSON serialization errors:
  1. Use the _validate_and_debug_prompt() method to analyze prompt issues
  2. Check for non-ASCII characters, very long lines, or unescaped quotes
  3. Test with minimal Claude options first
  4. Gradually add complexity to isolate the problem

  🚨 Error Symptoms:

  - ExceptionGroup: unhandled errors in a TaskGroup
  - json.decoder.JSONDecodeError: Unterminated string
  - CLIJSONDecodeError: Failed to decode JSON
  - Messages containing tool_use_id or tool_result in error logs

  💡 Remember:

  The Claude CLI integration uses subprocess calls to avoid JSON serialization issues. Always start with the minimal working configuration and
  avoid the problematic patterns listed above.

  This prompt captures the key learnings and provides clear guidance to avoid repeating this debugging process.
- When I ask you to lint, or when you decide on my own that you need to lint, always run ruff, black and mypy. We will refer to all as "linting".
- When I tell you about failed tests in the context of full-automation.sh, it's so you know, you are not supposed to run that script from your Claude context, they are two slow. You are going to research why they may fail in that context, run them individually to troubleshoot. Eventually, when ready, ask the user to run the full-automation.sh himself/herself
- For end to end test, integration tests, long running tests, that rely on real services, you are not going to stop or uninstall services, but rather on test setup you will ensure that what you need running (using the applications capabilities, don't manipulate containers from the outside) is running. If ollama is needed, and is not running because prior tests used voyage, you will stop, re-init adding ollama, and start services. If then services need Voyage, you will re-init, and ensure the collection is clean so the vector data matches the size of voyage vs. ollama. In essence, we are going to leave stuff running at the end of our tests, but ensure pre-requisites for our tests are met on test setup. The worst you can do is start uninstalling stuff at the end, you are making it harder for the next test and they are already slow to run.
- Tests that are part of our full-automation.sh script are relatively slow tests. To speed them up, we don't shutdown containers or services in the test teardown, but rather leave them running. Instead, the tests should have a comprehensive "setup" procedure that checks for pre-requesites to enable the test to execute properly. They can ensure containers are running (using high level functionality provided by our application, don't manipulate containers directly), they can cleanup or re-create qdrant collections, they can re-init the app with the proper params, and call "start" again if necessary, in esence, they ensure the conditions are properly set for the test to run properly. We are doing this as a strategy to accelerate test execution. In the past, we were tearing down everything on tear down of the test, and they take way too long to run. Keep this in mind any time you are writing an integration test, end to end e2e test, and any test that uses th real ollama, qdrant or voyage services.
- Ensure that slow, e2e, integration and any code that rely on Voyage AI API don't bleed into github actions and fast-automation.sh scripts. Those are supposed to be fast tests. All tests are discovered and run on full-automation.sh
- Every time you finish implementing a significant new feature or change, you will execute the lint.sh application, AND you will perform a comprehensive documentation check, the README.md file and the help, against what's implemented in the codebase. You will correct any errors, and you will do a second run after that.
- When working on improvements for the smart indexer, always consider the --reconcile function (non git-aware) and ensure consistency across both indexing processes. Treat the --reconcile aspect as equally important, maintaining feature parity and functionality, except for semantically specific module considerations.

## 🧪 Test Suite Architecture and GitHub Actions Analysis

### **Test Suite Types and Usage**

#### **1. `fast-automation.sh` - Comprehensive Local Unit Testing**
- **Purpose**: Comprehensive local unit test validation with full system access
- **Test Count**: 865+ tests  
- **Environment**: Local development with full file system permissions
- **Includes**: ALL unit tests including port registry tests (they work locally)
- **Execution Time**: ~2.5 minutes
- **Usage**: `./fast-automation.sh` - primary validation during development

#### **2. GitHub Actions CI (`.github/workflows/main.yml`) - Permission-Restricted Testing**
- **Purpose**: CI/CD validation in restricted GitHub environment
- **Test Count**: ~814 tests (excludes permission-dependent tests)
- **Environment**: GitHub Actions runners with limited system access
- **Excludes**: Tests requiring `/var/lib/code-indexer/` write permissions
- **Execution Time**: ~2 minutes per Python version (3.9, 3.10, 3.11, 3.12)
- **Restrictions**: Cannot write to system directories, no Docker/container access

#### **3. `full-automation.sh` - Complete Integration Testing**
- **Purpose**: Complete end-to-end testing with real services
- **Test Count**: All tests including E2E, integration, slow tests
- **Environment**: Local with full container/service access
- **Includes**: Everything - unit, integration, E2E, performance tests
- **Execution Time**: Much longer (10+ minutes)
- **Usage**: Complete validation before releases

### **GitHub Actions Test Exclusions - CRITICAL UNDERSTANDING**

When GitHub Actions tests fail, analyze the failure type:

#### **✅ VALID FAILURES (Must Fix)**
- Import errors due to code changes
- Constructor parameter mismatches after refactoring
- Logic errors in business functionality
- Configuration validation issues
- Test assertion failures due to actual bugs

#### **❌ EXPECTED FAILURES (Should Exclude from GitHub Actions)**

**Global Port Registry Permission Issues:**
```
PermissionError: [Errno 13] Permission denied: '/var/lib/code-indexer'
PortRegistryError: Global port registry not accessible
```
**Affected Tests:**
- `test_data_cleaner_health.py` - DockerManager instantiation
- `test_cleanup_validation.py` - DockerManager instantiation  
- `test_global_port_registry.py` - Direct port registry access
- `test_broken_softlink_cleanup.py` - Port registry cleanup operations
- `test_real_world_path_walking.py` - CLI status/init commands
- `test_cli_init_segment_size.py` - CLI init commands

**Container/Docker Access Issues:**
```
Cannot connect to Docker daemon
Container runtime not available
```

**File System Permission Issues:**
```
Permission denied: '/var/lib/'
Cannot create directory in system paths
```

### **ANALYSIS WORKFLOW - When GitHub Actions Fail**

#### **Step 1: Categorize the Failure**
- **Code Issue**: Fix the actual problem
- **Permission Issue**: Add to exclusion list in `.github/workflows/main.yml`
- **Environment Issue**: Verify if test belongs in CI vs local-only

#### **Step 2: Validate Local Behavior**  
- **Run `fast-automation.sh`**: Does the test pass locally?
- **If YES**: Environment issue, exclude from GitHub Actions
- **If NO**: Real bug, fix the test/code

#### **Step 3: Apply Appropriate Solution**
- **For real issues**: Fix code, update tests, ensure all environments pass
- **For permission issues**: Add `--ignore=path/to/test.py` to GitHub Actions workflow
- **Keep `fast-automation.sh` comprehensive**: Don't exclude tests from local testing

### **Key Principle: Differential Testing Strategy**

**GitHub Actions** = **Subset** of tests that work in restricted environments
**`fast-automation.sh`** = **Full** unit test coverage for local development  
**`full-automation.sh`** = **Complete** testing including integration/E2E

### **Common GitHub Actions Permission Failures (Auto-Exclude)**

```yaml
# In .github/workflows/main.yml - Current exclusions:
--ignore=tests/unit/infrastructure/test_data_cleaner_health.py
--ignore=tests/unit/infrastructure/test_cleanup_validation.py  
--ignore=tests/unit/infrastructure/test_global_port_registry.py
--ignore=tests/unit/infrastructure/test_broken_softlink_cleanup.py
--ignore=tests/unit/infrastructure/test_real_world_path_walking.py
--ignore=tests/unit/cli/test_cli_init_segment_size.py
--ignore=tests/unit/services/test_clean_file_chunking_manager.py
--ignore=tests/unit/services/test_file_chunking_manager.py
--ignore=tests/unit/services/test_file_chunk_batching_optimization.py
--ignore=tests/unit/services/test_voyage_threadpool_elimination.py
```

**Rule**: Any test that fails in GitHub Actions with permission errors OR requires external API keys (like VoyageAI) should be added to this exclusion list while being kept in `fast-automation.sh` for local testing.

**VoyageAI Integration Tests**: Tests that use real VoyageAI API calls are considered integration tests, not unit tests, and should not run in GitHub Actions without API credentials. They remain in fast-automation.sh for local development where API keys are available.

## **FULL-AUTOMATION.SH PYTHON COMMAND COMPATIBILITY**

**CRITICAL SYSTEM REQUIREMENT**: The `full-automation.sh` script must use `python3 -m pip` instead of bare `pip` commands to ensure compatibility with modern Python environments.

### **Python Command Issues and Solutions**

#### **Issue**: Modern Python environments may not have `python` command available
- **System Setup**: Many Linux distributions only provide `python3` command, not bare `python`
- **Error Symptom**: `./full-automation.sh: line 92: python: command not found`
- **Root Cause**: Script was using bare `pip` commands that may not be available

#### **Solution Implemented**:
```bash
# ❌ WRONG - May fail on systems without 'python' command
pip install -e ".[dev]" --break-system-packages

# ✅ CORRECT - Works with python3 environments
python3 -m pip install -e ".[dev]" --break-system-packages
```

### **Externally-Managed Environment Handling**

**Modern pip restriction**: Many distributions use externally-managed environments that prevent direct pip installations.

**Error Pattern**:
```
error: externally-managed-environment

× This environment is externally managed
╰─ To override this, use --break-system-packages
```

**Required Solution**: All pip commands MUST include `--break-system-packages` flag:
- `python3 -m pip install -e ".[dev]" --break-system-packages`
- `python3 -m pip install build twine --break-system-packages`

### **Script Command Audit Results**

**Fixed Commands in full-automation.sh**:
- Line 92: `python3 -m pip install -e ".[dev]" --break-system-packages`
- Line 326: `python3 -m pip install build twine --break-system-packages`

**Already Correct Commands**:
- Coverage commands: `python3 -m coverage xml`
- Build commands: `python3 -m build`

### **Testing Strategy for Script Compatibility**

**Test Coverage Implemented**:
- `tests/unit/scripts/test_full_automation_python_commands.py`: Comprehensive script validation
- `tests/unit/scripts/test_pip_command_issues.py`: Specific pip command compatibility testing

**Key Test Cases**:
- Python command availability verification
- Script syntax validation
- Externally-managed environment detection
- Pip command format verification (must use `python3 -m pip`)
- Error handling when script runs outside project root

### **Maintenance Guidelines**

**When adding new pip commands to full-automation.sh**:
1. ALWAYS use `python3 -m pip install` (never bare `pip install`)
2. ALWAYS include `--break-system-packages` flag
3. Test on systems where only `python3` is available
4. Add corresponding test cases for new pip usage patterns
- NEVER, EVER, remove functionality related to our enhanced processing of git projects. The git-awarness aspects, how we optimize processing branches, and keeping track of relationships, deduplication of indexing is what make this project unique. If you ever go into a refactoring rabbit hole and you will start removing functionality to that enables this capability you must stop, immediately, and ask if that's the true intent of the work you been asked to do.
- When working on fixing quick feedback unit tests, or fast tests, always use ./fast-automation.sh. This shell file is specifically tuned to run test that run fast, so they can be run efficiently from within Claude Code as a first layer of protection ensuring our tests pass and we didn't introduce regressions.
- When indexing, progress reporting is done real-time, in a single line at the bottom, showing a progress bar, and right next to it we show speed metrics and current file being processed. Don't change this approach without confirmation from the user. This is how it is, and it should be for all indexing operations, we don't show feedback scrolling the console, EVER, NEVER, EVER. Ask for confirmation if you are about to change this behavior. If the user ask you to change it, ask question, confirm the user is sure it wants to remove the single line, fixed to the bottom, progress bar, speed and currently file being processed.
- When asking to bump version, you will always check readme in case there's references to the version number, and you will always updte the release notes files with the latest changes
- In the context of this project, we don't use the /tmp folder as a temporary location. We use ~/.tmp
- The ports configuration in this project is "local", not "global". The local configuration is found walking folder structure upwards, like git does, and when we find out configuration file, that dictates everything, including ports of ALL of our containers. There's no shared containers among multiple projects, and a projet is defined as a location in the disk and all its subfolders where a config file can be found. Now, if there's another config file down the folder structure, that will override the config file found up the folder structure and it will have it's own containers. Our solution is multi-container, there's no "default ports", there's no "share containers". Containers are bound to a root folder that has a config file. Period. The code should NEVER, EVER, use "default ports". There's no such a thingg as default ports. Ports are ALWAYS dynamically calculated based on the project.
- When working on this project, it's absolutely critical to remember that we support both podman and docker. Development and most testing is done with podman, but there are docker-specific tests to verify no regressions occur. Docker usage is achieved in Docky Linux using the --force-docker flag.
- Our solution uses a per-project configuration and container set. Tests need to be aware of this. Many tests written before this big refactoring, were written with implied and hard-coded port numbers, they didn't reuse folders, making them inefficient and slow, some will start/stop containers manually, some e2e tests will tinker with internal calls rather than using the cidx (console) application directly (which is the right way to do it).
- The last step of every development engagement to implement a feature is to run fast-automation.sh. Only when it passes in full, we consider the task done.

- **🚨 VOYAGEAI BATCH PROCESSING TOKEN LIMITS**: VoyageAI API enforces 120,000 token limit per batch request. The VoyageAI client now implements token-aware batching that automatically splits large file batches to respect this limit while maintaining performance optimization. Files with >100K estimated tokens will be processed in multiple batches transparently. Error "max allowed tokens per submitted batch is 120000" indicates this protection is working correctly.

- CIDX SEMANTIC CODE SEARCH INTEGRATION

🎯 SEMANTIC SEARCH TOOL - YOUR PRIMARY CODE DISCOVERY METHOD

CRITICAL: You have access to a powerful semantic search tool `cidx query` that can find relevant code across the entire codebase. Use it liberally - it's much more effective than guessing or making assumptions.

**🧠 WHAT MAKES CIDX QUERY UNIQUE**:
- **Semantic Understanding**: Finds code related to concepts even when exact words don't match
- **Context Awareness**: Understands relationships between functions, classes, and modules  
- **Relevance Scoring**: Returns results ranked by semantic similarity (0.0-1.0 scale)
- **Git-Aware**: Searches within current project/branch context
- **Cross-Language**: Finds similar patterns across different programming languages

**WHEN TO USE CIDX QUERY**:
✅ "Where is X implemented?" → Search immediately with `cidx query "X implementation" --quiet`
✅ "How does Y work?" → Search for Y-related code first: `cidx query "Y functionality" --quiet`  
✅ "What files contain Z?" → Use semantic search: `cidx query "Z" --quiet`
✅ "Show me examples of..." → Search for examples: `cidx query "examples of..." --quiet`
✅ "Is there any code that..." → Search to verify: `cidx query "code that..." --quiet`
❌ "What is dependency injection?" → Can answer directly (general concept)

**ALWAYS USE --quiet FLAG**: This provides cleaner output without headers, making it easier to process results.

📖 COMPLETE CIDX QUERY COMMAND REFERENCE

```
Usage: cidx query [OPTIONS] QUERY

Search the indexed codebase using semantic similarity.

Performs AI-powered semantic search across your indexed code.
Uses vector embeddings to find conceptually similar code.

SEARCH CAPABILITIES:
  • Semantic search: Finds conceptually similar code
  • Natural language: Describe what you're looking for
  • Code patterns: Search for specific implementations
  • Git-aware: Searches within current project/branch context

FILTERING OPTIONS:
  • Language: --language python (searches only Python files)
  • Path: --path */tests/* (searches only test directories)
  • Score: --min-score 0.8 (only high-confidence matches)
  • Limit: --limit 20 (more results)
  • Accuracy: --accuracy high (higher accuracy, slower search)

Options:
  -l, --limit INTEGER             Number of results to return (default: 10)
  --language TEXT                 Filter by programming language (e.g., python, javascript)
  --path TEXT                     Filter by file path pattern (e.g., */tests/*)
  --min-score FLOAT               Minimum similarity score (0.0-1.0)
  --accuracy [fast|balanced|high] Search accuracy profile
  -q, --quiet                     Quiet mode - only show results, no headers
```

**🎯 SUPPORTED LANGUAGES** (use exact names for --language filter):
- **Backend**: `python`, `java`, `csharp`, `cpp`, `c`, `go`, `rust`, `php`
- **Frontend**: `javascript`, `typescript`, `html`, `css`, `vue`  
- **Mobile**: `swift`, `kotlin`, `dart`
- **Scripts**: `shell`, `sql`, `markdown`, `yaml`, `json`

🚀 STRATEGIC USAGE PATTERNS

**SEARCH BEST PRACTICES**:
- Use natural language queries that match developer intent
- Try multiple search terms if first search doesn't yield results
- Search for both implementation AND usage patterns
- Use specific technical terms from the domain/framework
- Search for error messages, function names, class names, etc.

**QUERY EFFECTIVENESS**:
- Instead of: "authentication"
- Try: "login user authentication", "auth middleware", "token validation"

**FILTERING STRATEGIES**:
- `--language python --quiet` - Focus on specific language
- `--path "*/tests/*" --quiet` - Find test patterns
- `--min-score 0.8 --quiet` - High-confidence matches only
- `--limit 20 --quiet` - Broader exploration
- `--accuracy high --quiet` - Maximum precision for complex queries

**📊 UNDERSTANDING SCORES**:
- **Score 0.9-1.0**: Highly relevant, exact concept matches
- **Score 0.7-0.8**: Very relevant, closely related implementations
- **Score 0.5-0.6**: Moderately relevant, similar patterns  
- **Score 0.3-0.4**: Loosely related, might provide context
- **Score < 0.3**: Minimal relevance, usually not useful

💡 PRACTICAL EXAMPLES (ALWAYS USE --quiet)

**Concept Discovery**:
- `cidx query "authentication mechanisms" --quiet`
- `cidx query "error handling patterns" --quiet`  
- `cidx query "data validation logic" --quiet`
- `cidx query "configuration management" --quiet`

**Implementation Finding**:
- `cidx query "API endpoint handlers" --language python --quiet`
- `cidx query "database queries" --language sql --limit 15 --quiet`
- `cidx query "async operations" --min-score 0.7 --quiet`
- `cidx query "REST API POST endpoint" --quiet`

**Testing & Quality**:
- `cidx query "unit test examples" --path "*/tests/*" --quiet`
- `cidx query "mock data creation" --limit 10 --quiet`
- `cidx query "integration test setup" --quiet`

**Architecture Exploration**:
- `cidx query "dependency injection setup" --quiet`
- `cidx query "microservice communication" --quiet`
- `cidx query "design patterns observer" --quiet`

**Multi-Step Discovery**:
1. Broad concept: `cidx query "user management" --quiet`
2. Narrow down: `cidx query "user authentication" --min-score 0.8 --quiet`
3. Find related: `cidx query "user permissions" --limit 5 --quiet`

**✅ SEMANTIC SEARCH vs ❌ TEXT SEARCH COMPARISON**:
✅ `cidx query "user authentication" --quiet` → Finds login, auth, security, credentials, sessions
❌ `grep "auth"` → Only finds literal "auth" text, misses related concepts

✅ `cidx query "error handling" --quiet` → Finds exceptions, try-catch, error responses, logging  
❌ `grep "error"` → Only finds "error" text, misses exception handling patterns
