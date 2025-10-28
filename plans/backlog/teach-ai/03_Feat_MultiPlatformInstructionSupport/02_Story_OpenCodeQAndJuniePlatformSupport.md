# Story: OpenCode, Q, and Junie Platform Support

## Story Overview

### User Story
As a developer using OpenCode, Amazon Q, or JetBrains Junie, I want to run `cidx teach-ai --<platform> --<scope>` so that my AI assistant has accurate cidx usage instructions in the platform-specific format and location.

### Value Delivered
Complete multi-platform teach-ai system supporting all 6 AI coding platforms with consistent interface and externalized template management.

### Story Points Indicators
- 🔧 Three platform handlers to implement
- 📁 Three template files to create
- ✅ Final story completing the epic
- 🚀 Full system validation

## Acceptance Criteria (Gherkin)

```gherkin
Feature: OpenCode, Q, and Junie Platform Support

Scenario: Create OpenCode instructions
  Given I have OpenCode configured
  When I run "cidx teach-ai --opencode --project"
  Then an AGENTS.md file is created in the project root
  And the content is loaded from prompts/ai_instructions/opencode.md template
  And the format follows AGENTS.md open standard per Story 0.1 research
  When I run "cidx teach-ai --opencode --global"
  Then the instruction file is created in the OpenCode global location
    | Expected Location | ~/.opencode/AGENTS.md (AGENTS.md open standard) |

Scenario: Create Amazon Q instructions
  Given I have Amazon Q configured
  When I run "cidx teach-ai --q --project"
  Then a cidx.md file is created in .amazonq/rules/ subdirectory
  And the content is loaded from prompts/ai_instructions/q.md template
  And the format follows Amazon Q workspace rule convention per Story 0.1 research
  When I run "cidx teach-ai --q --global"
  Then the instruction file is created in the Amazon Q global location
    | Expected Location | ~/.amazonq/rules/cidx.md (Amazon Q workspace rule) |

Scenario: Create JetBrains Junie instructions
  Given I have JetBrains Junie configured
  When I run "cidx teach-ai --junie --project"
  Then a guidelines.md file is created in .junie subdirectory
  And the content is loaded from prompts/ai_instructions/junie.md template
  And the format follows JetBrains IDE convention per Story 0.1 research
  When I run "cidx teach-ai --junie --global"
  Then the instruction file is created in the Junie global location
    | Expected Location | ~/.junie/guidelines.md (JetBrains IDE convention) |

Scenario: Complete platform documentation
  Given all 6 platforms are implemented
  When I run "cidx teach-ai --help"
  Then I see documentation for all 6 platform flags:
    | Flag        | Platform           | Status |
    | --claude    | Claude Code        | ✅     |
    | --codex     | GitHub Codex       | ✅     |
    | --gemini    | Google Gemini      | ✅     |
    | --opencode  | OpenCode           | ✅     |
    | --q         | Amazon Q           | ✅     |
    | --junie     | JetBrains Junie    | ✅     |
  And I see scope flag documentation:
    | Flag        | Purpose                      | Status |
    | --project   | Project-level instructions   | ✅     |
    | --global    | Global instructions          | ✅     |
  And I see optional flag documentation:
    | Flag        | Purpose                      | Status |
    | --show-only | Preview without writing      | ✅     |

Scenario: Template system completeness
  Given all template files exist
  When I modify any template in prompts/ai_instructions/
  And I regenerate instructions for that platform
  Then the changes are reflected without code changes
  And the system supports all 6 platforms seamlessly
```

## Implementation Tasks

### Task Checklist
- [x] Research OpenCode conventions (from Story 0.1)
- [x] Research Amazon Q conventions (from Story 0.1)
- [x] Research JetBrains Junie conventions (from Story 0.1)
- [x] Create OpenCodeHandler class
- [x] Create QHandler class
- [x] Create JunieHandler class
- [x] Create prompts/ai_instructions/opencode.md template
- [x] Create prompts/ai_instructions/q.md template
- [x] Create prompts/ai_instructions/junie.md template
- [x] Add remaining CLI flags (--opencode, --q, --junie)
- [x] Complete platform routing logic
- [x] Update --help with all platforms
- [x] Full system testing (all 6 platforms)
- [x] Create platform comparison documentation

### OpenCode Template Creation

Create `prompts/ai_instructions/opencode.md`:

```markdown
# CIDX Semantic Search for OpenCode

## Introduction
CIDX enhances OpenCode with powerful semantic code search capabilities, enabling intelligent code discovery beyond traditional text matching.

## Core Functionality

### Semantic Search Command
The primary command for code discovery is `cidx query` with various filtering options.

### Command Options
```bash
--quiet         # Minimal output (always recommended)
--limit N       # Number of results to return
--language X    # Filter by programming language
--path pattern  # Filter by file path pattern
--min-score N   # Minimum similarity threshold (0-1)
--accuracy high # Enhanced precision for complex queries
```

### Usage Guidelines
✅ **Use for:**
- Finding implementations: `cidx query "data validation logic" --quiet`
- Discovering patterns: `cidx query "singleton pattern" --quiet`
- Understanding architecture: `cidx query "service layer" --quiet`

❌ **Avoid for:**
- Exact string searches (use grep)
- Known file locations (navigate directly)

### Setup Instructions
```bash
# One-time setup
cidx init      # Initialize configuration
cidx start     # Start required services
cidx index     # Build semantic index

# Regular usage
cidx query "your search terms" --quiet
```

### Language Support
Full support for: Python, JavaScript, TypeScript, Java, Go, Rust, C++, C, PHP, Swift, Kotlin, Shell, SQL, YAML

### Interpreting Results
- **Score 0.9-1.0**: High confidence matches
- **Score 0.7-0.8**: Relevant results
- **Score 0.5-0.6**: Possibly relevant
- **Score <0.5**: Low relevance

### Search Techniques
1. Start with natural language queries
2. Use technical terms from your domain
3. Combine with filters for precision
4. Iterate based on initial results

### OpenCode Integration Examples
```bash
# Find all API endpoints
cidx query "REST API endpoints" --language python --quiet

# Locate database migrations
cidx query "database schema migrations" --path "*/migrations/*" --quiet

# Discover error handling patterns
cidx query "exception handling try catch" --min-score 0.8 --quiet
```

## Benefits
- Understands code intent, not just syntax
- Finds related code across files
- Supports natural language queries
- Accelerates code discovery
```

### Amazon Q Template Creation

Create `prompts/ai_instructions/q.md`:

```markdown
# CIDX Integration with Amazon Q

## Overview
CIDX provides enterprise-grade semantic code search capabilities that complement Amazon Q's AI-powered development assistance.

## Semantic Search Capabilities

### Primary Search Interface
```bash
cidx query "<search terms>" [options]
```

### Configuration Flags
| Flag | Description | Usage |
|------|-------------|-------|
| `--quiet` | Suppress verbose output | Always include |
| `--limit <n>` | Result count | Default: 10 |
| `--language <lang>` | Language filter | e.g., `--language java` |
| `--path <pattern>` | Path pattern | e.g., `--path "*/src/*"` |
| `--min-score <float>` | Score threshold | Range: 0.0-1.0 |
| `--accuracy high` | Precision mode | For critical searches |

### Enterprise Use Cases
✅ **Recommended:**
- Code review: `cidx query "security vulnerabilities" --quiet`
- Refactoring: `cidx query "deprecated methods" --quiet`
- Documentation: `cidx query "public API interfaces" --quiet`
- Compliance: `cidx query "data encryption" --quiet`

❌ **Not Recommended:**
- Configuration values (use grep)
- File paths (use find)

### Initial Setup
```bash
cidx init       # Configure project
cidx start      # Launch containers
cidx index      # Build index
cidx status     # Verify readiness
```

### Supported Technologies
- **Backend**: Java, Python, Go, Rust, PHP
- **Frontend**: JavaScript, TypeScript, Swift, Kotlin
- **Infrastructure**: Shell, YAML, SQL
- **Native**: C, C++

### Score Interpretation
```
0.90-1.00: Exact or near-exact semantic match
0.70-0.89: High relevance
0.50-0.69: Moderate relevance
0.00-0.49: Low relevance
```

### Enterprise Search Patterns

#### Security Audit
```bash
cidx query "authentication bypass" --min-score 0.7 --quiet
cidx query "SQL injection" --language java --quiet
cidx query "password storage" --accuracy high --quiet
```

#### Code Quality
```bash
cidx query "code duplication" --path "*/src/*" --quiet
cidx query "complex methods" --limit 20 --quiet
cidx query "test coverage gaps" --path "*/tests/*" --quiet
```

#### Architecture Review
```bash
cidx query "microservice boundaries" --quiet
cidx query "database connections" --language python --quiet
cidx query "API versioning" --min-score 0.8 --quiet
```

## Integration Benefits
- Semantic understanding of code intent
- Cross-repository search capabilities
- Natural language query support
- Enterprise-scale performance
```

### JetBrains Junie Template Creation

Create `prompts/ai_instructions/junie.md`:

```markdown
# CIDX for JetBrains Junie

## About This Integration
CIDX seamlessly integrates with JetBrains IDEs through Junie, providing advanced semantic code search that enhances IDE navigation and discovery capabilities.

## Semantic Search Features

### Base Command Structure
```bash
cidx query "<natural language query>" [options]
```

### Available Options
- `--quiet`: Minimal output mode (recommended)
- `--limit <number>`: Maximum results
- `--language <lang>`: Filter by language
- `--path <pattern>`: File path filtering
- `--min-score <0-1>`: Similarity threshold
- `--accuracy high`: Maximum precision

### IDE-Friendly Use Cases
✅ **Perfect for:**
- Finding implementations across large codebases
- Discovering usage patterns
- Locating similar code blocks
- Understanding system architecture

❌ **Use IDE search for:**
- Symbol navigation (Ctrl+Click)
- Text in current file (Ctrl+F)
- Known class/method names

### Project Initialization
1. Open terminal in project root
2. Run initialization sequence:
   ```bash
   cidx init    # Create configuration
   cidx start   # Start services
   cidx index   # Build semantic index
   ```
3. Verify with: `cidx status`

### Language Support Matrix
| Category | Languages |
|----------|-----------|
| JVM | Java, Kotlin, Scala |
| Web | JavaScript, TypeScript, HTML, CSS |
| Backend | Python, Go, Rust, PHP |
| Mobile | Swift, Objective-C |
| Data | SQL, JSON, YAML, XML |
| Systems | C, C++, Shell |

### Understanding Search Scores
- **1.0**: Exact semantic match
- **0.8-0.9**: Very similar code
- **0.6-0.7**: Related concepts
- **0.4-0.5**: Loosely related
- **<0.4**: Minimal relevance

### JetBrains Workflow Examples

#### Refactoring Support
```bash
# Find all usages of a pattern
cidx query "factory pattern implementation" --quiet

# Locate similar code for extraction
cidx query "user validation logic" --min-score 0.8 --quiet
```

#### Code Review
```bash
# Find potential issues
cidx query "TODO FIXME" --quiet
cidx query "deprecated API usage" --language java --quiet
```

#### Navigation Enhancement
```bash
# Find related components
cidx query "payment processing service" --quiet
cidx query "React hooks custom" --path "*/components/*" --quiet
```

#### Testing Support
```bash
# Discover test patterns
cidx query "mock service implementation" --path "*/test/*" --quiet
cidx query "integration test database" --language python --quiet
```

## IDE Integration Benefits
- Complements IDE's syntax-based search with semantic understanding
- Finds conceptually related code across project
- Natural language queries for complex searches
- No indexing lag - real-time after initial setup

## Tips for JetBrains Users
1. Use CIDX for concept discovery, IDE for navigation
2. Combine with IDE's structural search for best results
3. Keep index updated with `cidx index` after major changes
4. Use `--quiet` flag to reduce output noise in IDE terminal
```

### Handler Implementation

```pseudocode
# handlers/opencode_handler.py

class OpenCodeHandler(BaseAIHandler):
    """Handler for OpenCode platform using AGENTS.md open standard."""

    def get_platform_name(self) -> str:
        return "OpenCode"

    def get_project_filename(self) -> str:
        return "AGENTS.md"  # AGENTS.md open standard

    def get_global_directory(self) -> Path:
        # Based on Story 0.1 research - AGENTS.md open standard
        return Path.home() / ".opencode"

    def get_template_filename(self) -> str:
        return "opencode.md"


# handlers/q_handler.py

class QHandler(BaseAIHandler):
    """Handler for Amazon Q platform using workspace rule convention."""

    def get_platform_name(self) -> str:
        return "Amazon Q"

    def get_project_filename(self) -> str:
        return ".amazonq/rules/cidx.md"  # Amazon Q workspace rule

    def get_global_directory(self) -> Path:
        # Based on Story 0.1 research - workspace rule convention
        return Path.home() / ".amazonq" / "rules"

    def get_template_filename(self) -> str:
        return "q.md"


# handlers/junie_handler.py

class JunieHandler(BaseAIHandler):
    """Handler for JetBrains Junie platform using IDE convention."""

    def get_platform_name(self) -> str:
        return "JetBrains Junie"

    def get_project_filename(self) -> str:
        return ".junie/guidelines.md"  # JetBrains IDE convention

    def get_global_directory(self) -> Path:
        # Based on Story 0.1 research - JetBrains IDE convention
        return Path.home() / ".junie"

    def get_template_filename(self) -> str:
        return "junie.md"


# cli.py - Complete implementation

@cli.command("teach-ai")
@click.option("--claude", is_flag=True, help="Claude Code")
@click.option("--codex", is_flag=True, help="GitHub Codex")
@click.option("--gemini", is_flag=True, help="Google Gemini")
@click.option("--opencode", is_flag=True, help="OpenCode")  # NEW
@click.option("--q", is_flag=True, help="Amazon Q")  # NEW
@click.option("--junie", is_flag=True, help="JetBrains Junie")  # NEW
@click.option("--project", is_flag=True, help="Create in project root")
@click.option("--global", "global_scope", is_flag=True, help="Create in global directory")
@click.option("--show-only", is_flag=True, help="Preview without writing")
def teach_ai(claude, codex, gemini, opencode, q, junie, project, global_scope, show_only):
    """Generate AI platform instruction files for CIDX usage."""

    # Complete platform routing
    if claude:
        handler = ClaudeHandler()
    elif codex:
        handler = CodexHandler()
    elif gemini:
        handler = GeminiHandler()
    elif opencode:
        handler = OpenCodeHandler()  # NEW
    elif q:
        handler = QHandler()  # NEW
    elif junie:
        handler = JunieHandler()  # NEW
    else:
        click.echo("❌ Platform required: --claude, --codex, --gemini, --opencode, --q, or --junie")
        raise SystemExit(1)

    # ... rest of implementation ...
```

## Manual Testing

### Complete Test Matrix (All Platforms)

```
Full System Test Matrix:
══════════════════════════════════════════
Platform    Project  Global  Preview  Total
──────────────────────────────────────────
Claude      ✓        ✓       ✓        3
Codex       ✓        ✓       ✓        3
Gemini      ✓        ✓       ✓        3
OpenCode    ✓        ✓       ✓        3
Q           ✓        ✓       ✓        3
Junie       ✓        ✓       ✓        3
──────────────────────────────────────────
Total Tests:                          18

Template Modification Tests:           6
Error Handling Tests:                  3
──────────────────────────────────────────
Grand Total:                          27
```

### This Story's Test Scenarios

1. **OpenCode Tests** (AGENTS.md open standard)
   ```bash
   # Project scope
   cidx teach-ai --opencode --project
   test -f AGENTS.md && echo "✅ File created"

   # Global scope
   cidx teach-ai --opencode --global
   test -f ~/.opencode/AGENTS.md && echo "✅ Global file created"

   # Preview
   cidx teach-ai --opencode --show-only | head -5
   ```

2. **Amazon Q Tests** (workspace rule convention)
   ```bash
   # Project scope
   cidx teach-ai --q --project
   test -f .amazonq/rules/cidx.md && echo "✅ File created"

   # Global scope
   cidx teach-ai --q --global
   test -f ~/.amazonq/rules/cidx.md && echo "✅ Global file created"

   # Preview
   cidx teach-ai --q --show-only | grep "Amazon Q"
   ```

3. **JetBrains Junie Tests** (IDE convention)
   ```bash
   # Project scope
   cidx teach-ai --junie --project
   test -f .junie/guidelines.md && echo "✅ File created"

   # Global scope
   cidx teach-ai --junie --global
   test -f ~/.junie/guidelines.md && echo "✅ Global file created"

   # Preview
   cidx teach-ai --junie --show-only | grep "JetBrains"
   ```

4. **Complete System Validation**
   ```bash
   # Test all platforms in sequence
   for platform in claude codex gemini opencode q junie; do
     echo "Testing $platform..."
     cidx teach-ai --$platform --show-only | head -1
   done

   # Verify help documentation
   cidx teach-ai --help | grep -E "(claude|codex|gemini|opencode|q|junie)"
   ```

5. **Template System Validation**
   ```bash
   # Verify all templates exist
   ls -la prompts/ai_instructions/*.md
   # Should show: claude.md, codex.md, gemini.md, opencode.md, q.md, junie.md

   # Test template modification
   echo "# TEST MARKER" >> prompts/ai_instructions/q.md
   cidx teach-ai --q --project
   grep "TEST MARKER" .amazonq/rules/cidx.md && echo "✅ Template system works"
   ```

### Cross-Platform Validation
- [x] All 6 platforms have working handlers
- [x] All 6 template files exist and are populated
- [x] Project scope works for all platforms
- [x] Global scope works for all platforms
- [x] Preview mode works for all platforms
- [x] Backup functionality consistent across platforms
- [x] Error messages consistent across platforms
- [x] Performance remains < 500ms for all platforms

### Final System Checklist
- [x] Legacy "claude" command removed
- [x] New "teach-ai" command fully functional
- [x] All 6 platforms supported
- [x] Templates externalized and maintainable
- [x] Documentation complete
- [x] --help shows all options
- [x] README.md updated
- [x] fast-automation.sh passes

## Implementation Notes

### Platform-Specific File Conventions

**CRITICAL CONTEXT**: This story was written BEFORE Story 0.1 research findings were discovered. During implementation, we correctly followed the research-based platform conventions instead of initial story assumptions.

**Why Implementation Differs from Original Story:**

1. **OpenCode Platform**
   - **Story Initially Said**: "OPENCODE.md in project root"
   - **Implementation Delivers**: "AGENTS.md in project root"
   - **Rationale**: Story 0.1 research discovered OpenCode follows the AGENTS.md open standard, not a custom OPENCODE.md file
   - **Source**: AGENTS.md is an established convention in the AI tooling ecosystem

2. **Amazon Q Platform**
   - **Story Initially Said**: "Q.md in project root"
   - **Implementation Delivers**: ".amazonq/rules/cidx.md subdirectory"
   - **Rationale**: Story 0.1 research found Amazon Q uses workspace-specific rules in .amazonq/rules/ subdirectory
   - **Source**: Amazon Q official workspace rule convention

3. **JetBrains Junie Platform**
   - **Story Initially Said**: "JUNIE.md in project root"
   - **Implementation Delivers**: ".junie/guidelines.md subdirectory"
   - **Rationale**: Story 0.1 research confirmed JetBrains IDEs use .junie/guidelines.md convention
   - **Source**: JetBrains IDE configuration standards

**Production Readiness Status**: ✅ YES
- All 18 E2E tests passing
- Code follows actual platform conventions correctly
- Documentation now synchronized with implementation

**Documentation Synchronization**: This story file has been updated to reflect the correct (research-based) implementation rather than the initial assumptions.

## Definition of Done

### Story Completion Criteria
- ✅ OpenCodeHandler class implemented
- ✅ QHandler class implemented
- ✅ JunieHandler class implemented
- ✅ All 3 template files created with appropriate content
- ✅ CLI supports all 6 platform flags
- ✅ Complete platform routing logic
- ✅ Both scopes work for all new platforms
- ✅ Preview mode works for all platforms
- ✅ Help documentation complete
- ✅ All 27 test scenarios passing
- ✅ Epic fully complete

### Quality Gates
- All handlers follow consistent pattern
- No hardcoded instruction content anywhere
- Templates are platform-appropriate
- System supports 6 platforms seamlessly
- Performance consistent across all platforms
- Clean architecture with proper abstraction