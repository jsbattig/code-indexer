# Feature: Multi-Platform Instruction Support

## Feature Overview

### Purpose
Extend the teach-ai command to support 5 additional AI coding platforms (Codex, Gemini, OpenCode, Q, Junie), completing the multi-platform instruction generation system.

### Business Value
- **Complete Platform Coverage**: Support for all major AI coding assistants
- **Consistent Interface**: Single command works across all platforms
- **Maintainable Instructions**: Each platform has its own template file
- **Market Reach**: CIDX becomes compatible with entire AI coding ecosystem

### Success Criteria
- ✅ All 5 additional platforms have working teach-ai support
- ✅ Each platform has dedicated template file in prompts/ai_instructions/
- ✅ Platform-specific file naming and locations respected
- ✅ Both project and global scopes work for all platforms
- ✅ --help documentation covers all 6 platforms
- ✅ Consistent user experience across platforms

## Stories

### Story Tracking
- [ ] 01_Story_CodexAndGeminiPlatformSupport
- [ ] 02_Story_OpenCodeQAndJuniePlatformSupport

## Technical Architecture

### Multi-Platform Handler Architecture

```
┌─────────────────────────────────────────────┐
│           PlatformFactory                    │
│     Route to platform-specific handler       │
└────────────────┬────────────────────────────┘
                 │
    ┌────────────┼────────────┬────────────┐
    ▼            ▼            ▼            ▼
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│Claude  │  │Codex   │  │Gemini  │  │Others  │
│Handler │  │Handler │  │Handler │  │Handler │
└────────┘  └────────┘  └────────┘  └────────┘
    │            │            │            │
    ▼            ▼            ▼            ▼
claude.md   codex.md    gemini.md    *.md
```

### Platform Specifications

Based on Story 0.1 research findings:

```
Platform: GitHub Codex
- Project: ./CODEX.md
- Global: ~/.codex/CODEX.md (or per research)
- Format: Markdown
- Template: prompts/ai_instructions/codex.md

Platform: Google Gemini
- Project: ./GEMINI.md
- Global: ~/.gemini/GEMINI.md (or per research)
- Format: Markdown
- Template: prompts/ai_instructions/gemini.md

Platform: OpenCode
- Project: ./OPENCODE.md
- Global: ~/.opencode/OPENCODE.md (or per research)
- Format: Markdown
- Template: prompts/ai_instructions/opencode.md

Platform: Amazon Q
- Project: ./Q.md
- Global: ~/.q/Q.md (or per research)
- Format: Markdown
- Template: prompts/ai_instructions/q.md

Platform: JetBrains Junie
- Project: ./JUNIE.md
- Global: ~/.junie/JUNIE.md (or per research)
- Format: Markdown
- Template: prompts/ai_instructions/junie.md
```

### Handler Implementation Pattern

```pseudocode
class BaseAIHandler(ABC):
    """Abstract base class for all platform handlers."""

    @abstractmethod
    def get_platform_name() -> str:
        """Return platform display name."""

    @abstractmethod
    def get_project_filename() -> str:
        """Return project-level filename."""

    @abstractmethod
    def get_global_directory() -> Path:
        """Return global configuration directory."""

    @abstractmethod
    def get_template_filename() -> str:
        """Return template filename in prompts/ai_instructions/."""

    def get_instruction_content() -> str:
        """Load content from template file."""
        template_path = Path("prompts/ai_instructions") / self.get_template_filename()
        return template_path.read_text()

    def get_project_file_path() -> Path:
        """Get project-level file path."""
        return Path.cwd() / self.get_project_filename()

    def get_global_file_path() -> Path:
        """Get global file path."""
        global_dir = self.get_global_directory()
        global_dir.mkdir(exist_ok=True)
        return global_dir / self.get_project_filename()


class CodexHandler(BaseAIHandler):
    def get_platform_name(): return "GitHub Codex"
    def get_project_filename(): return "CODEX.md"
    def get_global_directory(): return Path.home() / ".codex"
    def get_template_filename(): return "codex.md"


class GeminiHandler(BaseAIHandler):
    def get_platform_name(): return "Google Gemini"
    def get_project_filename(): return "GEMINI.md"
    def get_global_directory(): return Path.home() / ".gemini"
    def get_template_filename(): return "gemini.md"

# Similar for OpenCode, Q, Junie handlers
```

### Template Content Adaptation

Each platform template will contain:
1. Platform-specific greeting/context
2. CIDX semantic search instructions (core content)
3. Platform-specific integration notes
4. Examples tailored to platform conventions

## Implementation Strategy

### Phase 1: Codex and Gemini (Story 2.1)
- Implement handlers for two most popular platforms
- Create and test template files
- Validate with actual platforms (if available)

### Phase 2: OpenCode, Q, and Junie (Story 2.2)
- Implement remaining three handlers
- Create remaining template files
- Complete multi-platform system

### Command Line Enhancement

```pseudocode
@cli.command("teach-ai")
@click.option("--claude", is_flag=True, help="Claude Code")
@click.option("--codex", is_flag=True, help="GitHub Codex")
@click.option("--gemini", is_flag=True, help="Google Gemini")
@click.option("--opencode", is_flag=True, help="OpenCode")
@click.option("--q", is_flag=True, help="Amazon Q")
@click.option("--junie", is_flag=True, help="JetBrains Junie")
# ... rest of implementation

# Platform routing
if claude:
    handler = ClaudeHandler()
elif codex:
    handler = CodexHandler()
elif gemini:
    handler = GeminiHandler()
elif opencode:
    handler = OpenCodeHandler()
elif q:
    handler = QHandler()
elif junie:
    handler = JunieHandler()
```

## Dependencies

### Upstream Dependencies
- Story 0.1: Platform research findings (file locations, formats)
- Story 1.1: Foundation and patterns from Claude implementation

### Downstream Impact
- Completes the teach-ai epic
- No downstream stories depend on this

## Testing Strategy

### Test Matrix

```
Platform × Scope × Action = Test Cases
6 platforms × 2 scopes × 2 actions = 24 test cases

Platforms: claude, codex, gemini, opencode, q, junie
Scopes: --project, --global
Actions: write, preview (--show-only)
```

### Manual Testing Protocol

For each platform:
1. Test project scope file creation
2. Test global scope file creation
3. Test preview mode
4. Test template modification
5. Verify with actual platform (if available)

### Validation Points
- Correct file names per platform
- Correct global directories
- Template content properly loaded
- Backup functionality works
- No hardcoded content

## Risk Mitigation

### Platform Availability Risk
- **Risk**: May not have all platforms for testing
- **Mitigation**: Focus on file creation and format correctness

### Convention Changes Risk
- **Risk**: Platform conventions may evolve
- **Mitigation**: Externalized templates allow easy updates

### Maintenance Risk
- **Risk**: 6 platforms to maintain
- **Mitigation**: Shared base class minimizes duplication

## Definition of Done

### Feature Completion Criteria
- ✅ All 5 additional platforms have handlers implemented
- ✅ All 5 template files created and populated
- ✅ Both scopes work for all platforms
- ✅ Preview mode works for all platforms
- ✅ --help documentation complete
- ✅ Test matrix fully executed
- ✅ No hardcoded instruction content

### Quality Gates
- Each platform handler follows same pattern
- Templates are maintainable by non-developers
- File operations are atomic with backup
- Command remains performant (< 500ms)
- Clear separation of concerns