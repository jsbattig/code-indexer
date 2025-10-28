# Feature: Claude Platform Instruction Management

## Feature Overview

### Purpose
Implement the teach-ai command for Claude platform with externalized template system, establishing the foundation for multi-platform support while removing the legacy "claude" command.

### Business Value
- **Immediate Claude Support**: Enables Claude Code users to benefit from cidx semantic search
- **Template System**: Establishes maintainable instruction management pattern
- **Legacy Cleanup**: Removes fragmented "claude" command implementation
- **Foundation Building**: Creates reusable patterns for other platforms

### Success Criteria
- ✅ `cidx teach-ai --claude --project` creates CLAUDE.md in project root
- ✅ `cidx teach-ai --claude --global` creates CLAUDE.md in ~/.claude/
- ✅ Template loaded from prompts/ai_instructions/claude.md
- ✅ Legacy "claude" command removed with migration message
- ✅ Template modifications require zero code changes
- ✅ Preview capability with --show-only flag

## Stories

### Story Tracking
- [ ] 01_Story_ClaudePlatformTeachAICommandWithTemplateSystem

## Technical Architecture

### Component Design

```
┌─────────────────────────────────────────────┐
│              CLI Command                     │
│      @cli.command("teach-ai")               │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│          Command Handler                     │
│   - Parse flags (--claude, --project, etc.) │
│   - Validate required flags                  │
│   - Route to appropriate handler             │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│         ClaudeHandler Class                  │
│   - get_instruction_content()                │
│   - get_project_file_path()                  │
│   - get_global_file_path()                   │
│   - write_instruction_file()                 │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│        Template File System                  │
│   prompts/ai_instructions/claude.md          │
│   (Externalized instruction content)         │
└─────────────────────────────────────────────┘
```

### File Operations Flow

```
Project Scope (--project):
1. Load template from prompts/ai_instructions/claude.md
2. Determine project root (current directory or git root)
3. Create/overwrite CLAUDE.md in project root
4. Backup existing file if present

Global Scope (--global):
1. Load template from prompts/ai_instructions/claude.md
2. Determine global directory (~/.claude/)
3. Create directory if not exists
4. Create/overwrite CLAUDE.md in global directory
5. Backup existing file if present

Preview Mode (--show-only):
1. Load template from prompts/ai_instructions/claude.md
2. Display content to console
3. Do not write any files
```

### Template Content Structure

```markdown
# CIDX Semantic Search Integration

## PRIMARY DISCOVERY TOOL
Use `cidx query` before grep/find for semantic searches.

## Key Flags
- `--limit N` (results)
- `--language python`
- `--path */tests/*`
- `--min-score 0.8`
- `--accuracy high`
- `--quiet` (always use)

## When to Use
✅ "Where is X implemented?"
✅ Concept/pattern discovery
✅ "How does Y work?"
❌ Exact string matches
❌ General concepts

## Initialization Workflow
1. `cidx init` - Initialize repository
2. `cidx start` - Start containers
3. `cidx index` - Build semantic index
4. `cidx query "search term"` - Search code

[Additional sections...]
```

## Implementation Details

### Command Line Interface

```pseudocode
@cli.command("teach-ai")
@click.option("--claude", flag=True, help="Generate Claude Code instructions")
@click.option("--project", flag=True, help="Create in project root")
@click.option("--global", flag=True, help="Create in global directory")
@click.option("--show-only", flag=True, help="Preview without writing")
def teach_ai_command(claude, project, global, show_only):
    # Validate platform flag
    if not claude:  # Will expand to check all platforms
        raise_error("Platform required: --claude")

    # Validate scope flag
    if not project and not global:
        raise_error("Scope required: --project or --global")

    # Route to handler
    handler = ClaudeHandler()

    # Execute action
    if show_only:
        handler.preview_instructions()
    elif project:
        handler.write_project_instructions()
    else:
        handler.write_global_instructions()
```

### ClaudeHandler Implementation

```pseudocode
class ClaudeHandler:
    def get_instruction_content():
        # Load from prompts/ai_instructions/claude.md
        template_path = Path("prompts/ai_instructions/claude.md")
        return template_path.read_text()

    def get_project_file_path():
        # Return Path to CLAUDE.md in project root
        return Path.cwd() / "CLAUDE.md"

    def get_global_file_path():
        # Return Path to ~/.claude/CLAUDE.md
        return Path.home() / ".claude" / "CLAUDE.md"

    def write_instruction_file(path):
        # Backup existing file
        if path.exists():
            backup_path = path.with_suffix(".md.backup")
            shutil.copy2(path, backup_path)

        # Write atomically
        content = self.get_instruction_content()
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(content)
        temp_path.replace(path)
```

### Legacy Command Removal

```pseudocode
# Remove from cli.py (lines 3779-4120)
@cli.command("claude")  # DELETE THIS ENTIRE COMMAND
def claude_command():
    # All this code to be removed
    ...

# Add deprecation handler
@cli.command("claude")
def claude_deprecated():
    click.echo("❌ Command 'claude' has been removed.")
    click.echo("Use 'cidx teach-ai --claude' instead.")
    raise SystemExit(1)
```

## Dependencies

### Upstream Dependencies
- Story 0.1: Research findings inform Claude global directory location

### Downstream Impact
- Foundation for Story 2.1 and 2.2 (other platforms)
- Establishes template loading pattern
- Sets file operation patterns

## Testing Strategy

### Manual E2E Testing

1. **Project Scope Test**
   ```bash
   cidx teach-ai --claude --project
   # Verify CLAUDE.md created in current directory
   # Verify content matches template
   ```

2. **Global Scope Test**
   ```bash
   cidx teach-ai --claude --global
   # Verify ~/.claude/CLAUDE.md created
   # Verify directory created if needed
   ```

3. **Preview Test**
   ```bash
   cidx teach-ai --claude --show-only
   # Verify content displayed
   # Verify no files written
   ```

4. **Template Modification Test**
   - Edit prompts/ai_instructions/claude.md
   - Regenerate instructions
   - Verify changes reflected

5. **Error Handling Tests**
   ```bash
   cidx teach-ai  # Missing platform
   cidx teach-ai --claude  # Missing scope
   cidx claude  # Legacy command
   ```

### Unit Testing Coverage
- Template file loading
- Path resolution (project vs global)
- Flag validation
- Backup file creation
- Atomic write operations

## Risk Mitigation

### Implementation Risks
- **Template File Missing**: Check existence, provide helpful error
- **Permission Denied**: Handle gracefully with clear message
- **Existing File Overwrite**: Always create backup first

### Migration Risks
- **Users Using Legacy Command**: Clear deprecation message
- **Muscle Memory**: Helpful error pointing to new command

## Definition of Done

### Feature Completion Criteria
- ✅ teach-ai command implemented for Claude platform
- ✅ Template system working with external .md file
- ✅ Both project and global scopes functional
- ✅ Preview mode operational
- ✅ Legacy "claude" command removed
- ✅ Error messages clear and helpful
- ✅ Claude Code recognizes generated files

### Quality Gates
- No hardcoded instruction content in Python
- Template modifications work without code changes
- All file operations are atomic
- Existing files are backed up
- Command executes in < 500ms