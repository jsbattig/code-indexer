# Story: Codex and Gemini Platform Support

## Story Overview

### User Story
As a developer using GitHub Codex or Google Gemini, I want to run `cidx teach-ai --codex --<scope>` or `cidx teach-ai --gemini --<scope>` so that my AI assistant has accurate cidx usage instructions in the platform-specific format and location.

### Value Delivered
Working teach-ai support for Codex and Gemini platforms with platform-specific conventions and externalized templates.

### Story Points Indicators
- 🔧 Two platform handlers to implement
- 📁 Two template files to create
- ✅ Reuse patterns from Claude implementation

## Acceptance Criteria (Gherkin)

```gherkin
Feature: Codex and Gemini Platform Support

Scenario: Create Codex project instructions
  Given I have GitHub Codex configured
  When I run "cidx teach-ai --codex --project"
  Then a CODEX.md file is created in the project root
  And the content is loaded from prompts/ai_instructions/codex.md template
  And the format follows Codex conventions per Story 0.1 research

Scenario: Create Codex global instructions
  Given I want global Codex instructions
  When I run "cidx teach-ai --codex --global"
  Then the instruction file is created in the Codex global location
    | Expected Location | Per Story 0.1 research (e.g., ~/.codex/CODEX.md) |
  And the directory is created if it doesn't exist
  And existing files are backed up to .backup before overwrite

Scenario: Create Gemini project instructions
  Given I have Google Gemini configured
  When I run "cidx teach-ai --gemini --project"
  Then a GEMINI.md file is created in the project root
  And the content is loaded from prompts/ai_instructions/gemini.md template
  And the format follows Gemini conventions per Story 0.1 research

Scenario: Create Gemini global instructions
  Given I want global Gemini instructions
  When I run "cidx teach-ai --gemini --global"
  Then the instruction file is created in the Gemini global location
    | Expected Location | Per Story 0.1 research (e.g., ~/.gemini/GEMINI.md) |
  And the directory is created if it doesn't exist
  And existing files are backed up before overwrite

Scenario: Preview content for both platforms
  Given I want to preview content for either platform
  When I run "cidx teach-ai --codex --show-only"
  Then the Codex instruction content is displayed
  And no files are written
  When I run "cidx teach-ai --gemini --show-only"
  Then the Gemini instruction content is displayed
  And no files are written

Scenario: Template modification without code changes
  Given the template files exist
  When I modify prompts/ai_instructions/codex.md
  And I run "cidx teach-ai --codex --project"
  Then the generated CODEX.md reflects the changes
  When I modify prompts/ai_instructions/gemini.md
  And I run "cidx teach-ai --gemini --project"
  Then the generated GEMINI.md reflects the changes
  And no Python code changes were required
```

## Implementation Tasks

### Task Checklist
- [x] Research Codex file conventions (from Story 0.1)
- [x] Research Gemini file conventions (from Story 0.1)
- [x] Create CodexHandler class
- [x] Create GeminiHandler class
- [x] Create prompts/ai_instructions/codex.md template
- [x] Create prompts/ai_instructions/gemini.md template
- [x] Add --codex flag to CLI command
- [x] Add --gemini flag to CLI command
- [x] Update platform routing logic
- [x] Test all combinations (2 platforms × 2 scopes)
- [x] Update --help documentation
- [x] Manual E2E testing

### Codex Template Creation

Create `prompts/ai_instructions/codex.md`:

```markdown
# CIDX Integration for GitHub Codex

## Overview
This document provides instructions for using CIDX semantic code search within GitHub Codex projects.

## Semantic Code Search with CIDX

### Primary Discovery Tool
Use `cidx query` for semantic searches before falling back to text-based search.

### Key Command Flags
- `--limit N`: Number of results (default: 10)
- `--language <lang>`: Filter by programming language
- `--path <pattern>`: Filter by file path pattern
- `--min-score <float>`: Minimum similarity score (0.0-1.0)
- `--accuracy high`: Enhanced precision mode
- `--quiet`: Minimal output (recommended)

### When to Use CIDX Query
✅ Finding implementation patterns: `cidx query "database connection handling" --quiet`
✅ Discovering related code: `cidx query "user authentication flow" --quiet`
✅ Understanding functionality: `cidx query "payment processing" --quiet`
❌ Exact string matches: Use traditional grep/search
❌ Known file locations: Navigate directly

### Setup Workflow
1. Initialize: `cidx init`
2. Start services: `cidx start`
3. Index codebase: `cidx index`
4. Query: `cidx query "your search term" --quiet`

### Language Support
Python, JavaScript, TypeScript, Java, Go, Rust, C++, C, PHP, Swift, Kotlin, Shell, SQL, YAML

### Relevance Scoring
- 0.9-1.0: Highly relevant matches
- 0.7-0.8: Good matches
- 0.5-0.6: Potentially relevant
- <0.5: Lower relevance

### Search Strategies
- Start broad: `cidx query "feature area" --quiet`
- Narrow with filters: `--language python --path "*/api/*"`
- Combine terms: `cidx query "REST API error handling" --quiet`

### Examples for Codex Integration
```bash
# Find API endpoints
cidx query "API route handlers" --language python --quiet

# Discover test patterns
cidx query "unit test mocking" --path "*/tests/*" --quiet

# Locate configuration
cidx query "database configuration" --min-score 0.8 --quiet
```

## Benefits Over Traditional Search
- Understands code semantics, not just text matching
- Finds conceptually related code across files
- Reduces time spent searching for implementations
```

### Gemini Template Creation

Create `prompts/ai_instructions/gemini.md`:

```markdown
# CIDX Integration for Google Gemini

## About CIDX
CIDX provides semantic code search capabilities that enhance Gemini's ability to understand and navigate codebases efficiently.

## Using Semantic Search

### Primary Search Method
Always attempt `cidx query` before using text-based search methods.

### Essential Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--quiet` | Minimal output | Always include |
| `--limit N` | Result count | `--limit 20` |
| `--language` | Language filter | `--language typescript` |
| `--path` | Path pattern | `--path "*/components/*"` |
| `--min-score` | Score threshold | `--min-score 0.75` |
| `--accuracy high` | Precision mode | For complex queries |

### Appropriate Use Cases
✅ **Concept Discovery**: Finding code by functionality
✅ **Pattern Search**: Locating implementation patterns
✅ **Architecture Understanding**: Discovering system components
❌ **Variable Names**: Use grep for exact matches
❌ **String Literals**: Use text search for specific strings

### Initialization Process
```bash
cidx init     # Configure repository
cidx start    # Launch containers
cidx index    # Build semantic index
cidx query "search terms" --quiet  # Search
```

### Supported Languages
- Backend: Python, Java, Go, Rust, PHP
- Frontend: JavaScript, TypeScript, Swift, Kotlin
- Systems: C, C++, Shell
- Data: SQL, YAML

### Understanding Scores
Scores indicate semantic similarity:
- **0.9+**: Nearly identical concepts
- **0.7-0.8**: Strong relevance
- **0.5-0.6**: Moderate relevance
- **<0.5**: Weak relevance

### Effective Query Patterns
1. **Broad to Specific**
   - Start: `cidx query "authentication" --quiet`
   - Refine: `cidx query "OAuth token validation" --quiet`

2. **Component Discovery**
   ```bash
   cidx query "database models" --language python --quiet
   cidx query "React components" --path "*/components/*" --quiet
   ```

3. **Testing Patterns**
   ```bash
   cidx query "integration tests" --path "*/tests/*" --quiet
   cidx query "mock services" --language javascript --quiet
   ```

## Advantages
- Semantic understanding beyond keyword matching
- Cross-file relationship discovery
- Natural language query support
- Faster codebase exploration
```

### Handler Implementation

```pseudocode
# handlers/codex_handler.py

class CodexHandler(BaseAIHandler):
    """Handler for GitHub Codex platform."""

    def get_platform_name(self) -> str:
        return "GitHub Codex"

    def get_project_filename(self) -> str:
        return "CODEX.md"

    def get_global_directory(self) -> Path:
        # Based on Story 0.1 research findings
        return Path.home() / ".codex"  # Or actual finding

    def get_template_filename(self) -> str:
        return "codex.md"


# handlers/gemini_handler.py

class GeminiHandler(BaseAIHandler):
    """Handler for Google Gemini platform."""

    def get_platform_name(self) -> str:
        return "Google Gemini"

    def get_project_filename(self) -> str:
        return "GEMINI.md"

    def get_global_directory(self) -> Path:
        # Based on Story 0.1 research findings
        return Path.home() / ".gemini"  # Or actual finding

    def get_template_filename(self) -> str:
        return "gemini.md"


# cli.py updates

@cli.command("teach-ai")
@click.option("--claude", is_flag=True, help="Claude Code")
@click.option("--codex", is_flag=True, help="GitHub Codex")  # NEW
@click.option("--gemini", is_flag=True, help="Google Gemini")  # NEW
# ... other options ...
def teach_ai(claude, codex, gemini, ...):
    # ... validation logic ...

    # Extended platform routing
    if claude:
        handler = ClaudeHandler()
    elif codex:
        handler = CodexHandler()  # NEW
    elif gemini:
        handler = GeminiHandler()  # NEW
    # ... rest of implementation ...
```

## Manual Testing

### Test Matrix for This Story

```
Codex Tests:
1. cidx teach-ai --codex --project     → CODEX.md in project
2. cidx teach-ai --codex --global      → ~/.codex/CODEX.md
3. cidx teach-ai --codex --show-only   → Preview only

Gemini Tests:
4. cidx teach-ai --gemini --project    → GEMINI.md in project
5. cidx teach-ai --gemini --global     → ~/.gemini/GEMINI.md
6. cidx teach-ai --gemini --show-only  → Preview only

Template Tests:
7. Modify codex.md template → Regenerate → Verify changes
8. Modify gemini.md template → Regenerate → Verify changes
```

### Detailed Test Scenarios

1. **Codex Project Scope**
   ```bash
   cd /tmp/test-project
   cidx teach-ai --codex --project
   cat CODEX.md
   # Verify: Content matches codex.md template
   # Verify: File named CODEX.md (not codex.md)
   ```

2. **Codex Global Scope**
   ```bash
   cidx teach-ai --codex --global
   ls -la ~/.codex/
   cat ~/.codex/CODEX.md
   # Verify: Directory created if needed
   # Verify: Content correct
   ```

3. **Gemini Project Scope**
   ```bash
   cd /tmp/test-project
   cidx teach-ai --gemini --project
   cat GEMINI.md
   # Verify: Content matches gemini.md template
   ```

4. **Gemini Global Scope**
   ```bash
   cidx teach-ai --gemini --global
   ls -la ~/.gemini/
   cat ~/.gemini/GEMINI.md
   # Verify: Directory created if needed
   ```

5. **Backup Functionality**
   ```bash
   echo "old" > CODEX.md
   cidx teach-ai --codex --project
   cat CODEX.md.backup
   # Verify: Backup contains "old"
   ```

6. **Template Modification**
   ```bash
   # Add "TEST MARKER" to prompts/ai_instructions/codex.md
   cidx teach-ai --codex --project
   grep "TEST MARKER" CODEX.md
   # Verify: Marker present in output
   ```

### Platform Integration Testing
If platforms are available:
1. Generate instruction files
2. Open Codex/Gemini in test project
3. Verify platforms recognize instruction files
4. Test if instructions are followed

### Validation Checklist
- [ ] Codex handler implemented
- [ ] Gemini handler implemented
- [ ] Codex template created
- [ ] Gemini template created
- [ ] CLI flags added for both platforms
- [ ] Project scope works for both
- [ ] Global scope works for both
- [ ] Preview mode works for both
- [ ] Backup functionality works
- [ ] Template modifications work
- [ ] Help documentation updated

## Definition of Done

### Story Completion Criteria
- ✅ CodexHandler class implemented
- ✅ GeminiHandler class implemented
- ✅ Both template files created with platform-specific content
- ✅ CLI supports --codex and --gemini flags
- ✅ Both project and global scopes functional
- ✅ Preview mode operational for both platforms
- ✅ Template modification works without code changes
- ✅ All 6 test scenarios passing
- ✅ Documentation updated

### Quality Gates
- Handlers follow established pattern from Claude
- No hardcoded instruction content
- Templates are clear and platform-appropriate
- File operations remain atomic with backup
- Performance stays under 500ms