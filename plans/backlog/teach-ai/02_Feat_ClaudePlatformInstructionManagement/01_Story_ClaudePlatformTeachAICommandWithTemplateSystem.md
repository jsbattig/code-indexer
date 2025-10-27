# Story: Claude Platform teach-ai Command with Template System

## Story Overview

### User Story
As a developer using Claude Code, I want to run `cidx teach-ai --claude --project` or `cidx teach-ai --claude --global` so that Claude Code automatically receives up-to-date instructions on how to use cidx for semantic code search, with instruction content managed in external template files that non-developers can update.

### Value Delivered
Working teach-ai command for Claude platform with externalized template system, enabling instruction updates without code changes, and complete removal of legacy "claude" command.

### Story Points Indicators
- 🔧 New command implementation
- 📁 File system operations
- ✅ Template system setup
- 🔄 Legacy code removal

## Acceptance Criteria (Gherkin)

```gherkin
Feature: Claude Platform teach-ai Command

Scenario: Create project-level Claude instructions
  Given I have cidx installed in my project
  When I run "cidx teach-ai --claude --project"
  Then a CLAUDE.md file is created in the project root
  And the content is loaded from prompts/ai_instructions/claude.md template
  And the file contains cidx usage instructions:
    | Section                  | Content                                         |
    | Semantic search overview | How cidx query works                          |
    | Initialization steps     | cidx init, start, index workflow              |
    | Query command usage     | Examples with key flags                        |
    | Key flags               | --limit, --language, --path, --min-score      |
    | Best practices          | When to use semantic vs text search           |

Scenario: Create global Claude instructions
  Given I have Claude Code configured globally
  When I run "cidx teach-ai --claude --global"
  Then a CLAUDE.md file is created/updated in ~/.claude/
  And the directory ~/.claude/ is created if it doesn't exist
  And the content matches the project template
  And existing file is backed up to CLAUDE.md.backup before overwrite

Scenario: Template system functionality
  Given the template file prompts/ai_instructions/claude.md exists
  When I modify the template content without touching Python code
  And I run "cidx teach-ai --claude --project"
  Then the generated CLAUDE.md reflects the updated template content
  And no Python code changes were required

Scenario: Preview instruction content
  Given I want to preview instruction content
  When I run "cidx teach-ai --claude --show-only"
  Then the instruction content is displayed to console
  And no files are written to the file system
  And the output shows the full template content

Scenario: Validate required flags
  Given I run the command without required flags
  When I run "cidx teach-ai" without platform flag
  Then I see error: "❌ Platform required: --claude, --codex, --gemini, --opencode, --q, or --junie"
  When I run "cidx teach-ai --claude" without scope flag
  Then I see error: "❌ Scope required: --project or --global"

Scenario: Legacy command removal
  Given the new teach-ai command is implemented
  When I run "cidx claude" (legacy command)
  Then I see error: "❌ Command 'claude' has been removed. Use 'cidx teach-ai --claude' instead."
  And the legacy command code is removed from cli.py
```

## Implementation Tasks

### Task Checklist
- [ ] Create teach-ai command in CLI
- [ ] Implement flag validation (platform and scope required)
- [ ] Create ClaudeHandler class
- [ ] Create template file prompts/ai_instructions/claude.md
- [ ] Implement project scope file creation
- [ ] Implement global scope file creation
- [ ] Implement preview mode (--show-only)
- [ ] Add backup functionality for existing files
- [ ] Remove legacy "claude" command from cli.py
- [ ] Add deprecation message for legacy command
- [ ] Update --help documentation
- [ ] Manual E2E testing

### Template File Creation

Create `prompts/ai_instructions/claude.md`:

```markdown
# CIDX Semantic Search Integration

## PRIMARY DISCOVERY TOOL
Use `cidx query` before grep/find for semantic searches.

## Key Flags
- `--limit N` (results count, default 10)
- `--language python` (filter by language)
- `--path */tests/*` (filter by path pattern)
- `--min-score 0.8` (similarity threshold)
- `--accuracy high` (higher precision)
- `--quiet` (minimal output - always use)

## When to Use
✅ "Where is X implemented?" → `cidx query "X implementation" --quiet`
✅ Concept/pattern discovery → Semantic search finds related code
✅ "How does Y work?" → `cidx query "Y functionality" --quiet`
❌ Exact string matches (var names, config values) → Use grep/find
❌ General concepts you can answer directly → No search needed

## Initialization Workflow
Before using semantic search, initialize the repository:
1. `cidx init` - Initialize repository configuration
2. `cidx start` - Start required containers (Qdrant, etc.)
3. `cidx index` - Build semantic index of codebase
4. `cidx query "search term"` - Perform semantic searches

## Supported Languages
python, javascript, typescript, java, go, rust, cpp, c, php, swift, kotlin, shell, sql, yaml

## Score Interpretation
- 0.9-1.0: Exact/near-exact match
- 0.7-0.8: Very relevant
- 0.5-0.6: Moderately relevant
- <0.3: Likely noise

## Search Best Practices
- Use natural language queries matching developer intent
- Try multiple search terms if first search doesn't yield results
- Search for both implementation AND usage patterns
- Use specific technical terms from domain/framework

## Query Effectiveness Examples
- Instead of: "authentication"
- Try: "login user authentication", "auth middleware", "token validation"

## Filtering Strategies
- `--language python --quiet` - Focus on specific language
- `--path "*/tests/*" --quiet` - Find test patterns
- `--min-score 0.8 --quiet` - High-confidence matches only
- `--limit 20 --quiet` - Broader exploration
- `--accuracy high --quiet` - Maximum precision for complex queries

## Practical Examples (ALWAYS USE --quiet)
- Concept: `cidx query "authentication mechanisms" --quiet`
- Implementation: `cidx query "API endpoint handlers" --language python --quiet`
- Testing: `cidx query "unit test examples" --path "*/tests/*" --quiet`
- Multi-step: Broad search → Narrow down with filters

## Semantic vs Text Search Comparison
✅ `cidx query "user authentication" --quiet` → Finds login, auth, security, sessions
❌ `grep "auth"` → Only finds literal "auth" text, misses related concepts
```

### Implementation Pseudocode

```pseudocode
# cli.py additions

@cli.command("teach-ai")
@click.option("--claude", is_flag=True)
@click.option("--codex", is_flag=True)  # Future
@click.option("--gemini", is_flag=True)  # Future
@click.option("--opencode", is_flag=True)  # Future
@click.option("--q", is_flag=True)  # Future
@click.option("--junie", is_flag=True)  # Future
@click.option("--project", is_flag=True)
@click.option("--global", is_flag=True)
@click.option("--show-only", is_flag=True)
def teach_ai(claude, codex, gemini, opencode, q, junie, project, global_scope, show_only):
    """Generate AI platform instruction files for CIDX usage."""

    # Validate platform selection
    platforms = [claude, codex, gemini, opencode, q, junie]
    selected = [p for p in platforms if p]

    if len(selected) == 0:
        click.echo("❌ Platform required: --claude, --codex, --gemini, --opencode, --q, or --junie")
        raise SystemExit(1)

    if len(selected) > 1:
        click.echo("❌ Only one platform can be selected at a time")
        raise SystemExit(1)

    # Validate scope selection (unless preview mode)
    if not show_only and not project and not global_scope:
        click.echo("❌ Scope required: --project or --global")
        raise SystemExit(1)

    # Route to appropriate handler
    if claude:
        handler = ClaudeHandler()
    # Future: elif codex: handler = CodexHandler()
    # etc.

    # Execute action
    if show_only:
        content = handler.get_instruction_content()
        click.echo(content)
    elif project:
        handler.write_project_instructions()
        click.echo("✅ Created CLAUDE.md in project root")
    else:  # global
        handler.write_global_instructions()
        click.echo("✅ Created CLAUDE.md in ~/.claude/")


# handlers/claude_handler.py

class ClaudeHandler:
    def __init__(self):
        self.template_path = Path(__file__).parent.parent / "prompts" / "ai_instructions" / "claude.md"

    def get_instruction_content(self) -> str:
        """Load instruction content from template file."""
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template not found: {self.template_path}")
        return self.template_path.read_text(encoding="utf-8")

    def get_project_file_path(self) -> Path:
        """Get path for project-level instruction file."""
        return Path.cwd() / "CLAUDE.md"

    def get_global_file_path(self) -> Path:
        """Get path for global instruction file."""
        global_dir = Path.home() / ".claude"
        global_dir.mkdir(exist_ok=True)
        return global_dir / "CLAUDE.md"

    def _write_with_backup(self, path: Path, content: str):
        """Write file with atomic operation and backup."""
        # Backup existing file
        if path.exists():
            backup_path = path.with_suffix(".md.backup")
            shutil.copy2(path, backup_path)

        # Atomic write
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)

    def write_project_instructions(self):
        """Write instructions to project root."""
        path = self.get_project_file_path()
        content = self.get_instruction_content()
        self._write_with_backup(path, content)

    def write_global_instructions(self):
        """Write instructions to global directory."""
        path = self.get_global_file_path()
        content = self.get_instruction_content()
        self._write_with_backup(path, content)


# Legacy command deprecation
@cli.command("claude")
def claude_deprecated():
    """Deprecated command - replaced by teach-ai."""
    click.echo("❌ Command 'claude' has been removed.")
    click.echo("Use 'cidx teach-ai --claude' instead.")
    click.echo("")
    click.echo("Examples:")
    click.echo("  cidx teach-ai --claude --project  # Create CLAUDE.md in project")
    click.echo("  cidx teach-ai --claude --global   # Create CLAUDE.md globally")
    click.echo("  cidx teach-ai --claude --show-only # Preview content")
    raise SystemExit(1)
```

## Manual Testing

### Test Scenarios

1. **Project Scope Creation**
   ```bash
   cd /tmp/test-project
   cidx teach-ai --claude --project
   # Verify: CLAUDE.md exists in /tmp/test-project/
   # Verify: Content matches template
   ```

2. **Global Scope Creation**
   ```bash
   cidx teach-ai --claude --global
   # Verify: ~/.claude/ directory exists
   # Verify: ~/.claude/CLAUDE.md exists
   # Verify: Content matches template
   ```

3. **Backup on Overwrite**
   ```bash
   echo "old content" > CLAUDE.md
   cidx teach-ai --claude --project
   # Verify: CLAUDE.md.backup contains "old content"
   # Verify: CLAUDE.md has new content
   ```

4. **Preview Mode**
   ```bash
   cidx teach-ai --claude --show-only
   # Verify: Content displayed to terminal
   # Verify: No files created/modified
   ```

5. **Template Modification**
   ```bash
   # Edit prompts/ai_instructions/claude.md
   # Add "TEST MODIFICATION" to template
   cidx teach-ai --claude --project
   # Verify: CLAUDE.md contains "TEST MODIFICATION"
   ```

6. **Error Cases**
   ```bash
   cidx teach-ai
   # Verify: Error about missing platform flag

   cidx teach-ai --claude
   # Verify: Error about missing scope flag

   cidx claude
   # Verify: Deprecation message with migration instructions
   ```

7. **Claude Code Integration**
   ```bash
   cidx teach-ai --claude --project
   # Open Claude Code in project
   # Verify: Claude recognizes and uses CLAUDE.md instructions
   ```

### Validation Checklist
- [ ] Project scope file creation works
- [ ] Global scope file creation works
- [ ] Directory creation for global scope works
- [ ] Backup functionality works
- [ ] Preview mode works without writing files
- [ ] Template modifications reflected without code changes
- [ ] Error messages are clear and helpful
- [ ] Legacy command shows deprecation message
- [ ] Claude Code recognizes instruction files
- [ ] Command executes in < 500ms

## Definition of Done

### Story Completion Criteria
- ✅ teach-ai command implemented with --claude flag
- ✅ Both --project and --global scopes functional
- ✅ Template file created at prompts/ai_instructions/claude.md
- ✅ Template loading works dynamically
- ✅ --show-only preview mode operational
- ✅ Backup created for existing files
- ✅ Legacy "claude" command removed from cli.py
- ✅ Deprecation handler added with helpful message
- ✅ All manual tests passing
- ✅ Claude Code successfully using generated instructions

### Quality Gates
- No hardcoded instruction content in Python code
- Template can be modified without code changes
- All file operations are atomic
- Clear error messages for all failure paths
- Command performance < 500ms