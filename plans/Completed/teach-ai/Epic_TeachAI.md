# Epic: Teach AI - Multi-Platform AI Coding Assistant Instruction System

## Epic Overview

### Problem Statement
CIDX needs to maintain AI coding agent instruction files (CLAUDE.md and platform equivalents) that teach AI assistants how to use cidx effectively. The current "claude" command is limited and Claude-specific. We need to replace it with a broader "teach-ai" system that supports multiple AI platforms with externalized, maintainable instruction templates.

### Users
- Developers using Claude Code for AI-assisted development
- Developers using GitHub Codex for code generation
- Developers using Google Gemini for coding tasks
- Developers using OpenCode for open-source AI assistance
- Developers using Amazon Q for enterprise development
- Developers using JetBrains Junie for IDE-integrated AI

### Business Value
- **Unified Multi-Platform Support**: Single command supports 6 different AI coding platforms
- **Maintainable Instructions**: Externalized templates allow non-developers to update content
- **Consistent Experience**: Standardized interface across all AI platforms
- **Legacy Cleanup**: Complete removal of fragmented "claude" command
- **Semantic Search Adoption**: Teaches AI agents to leverage cidx's semantic capabilities

### Success Criteria
- ✅ CIDX generates instruction files for all 6 supported AI platforms
- ✅ Single `cidx teach-ai` command with platform and scope flags
- ✅ Instructions maintained in external .md templates (not hardcoded)
- ✅ Legacy "claude" command completely removed from codebase
- ✅ Project-level and global instruction file support
- ✅ Platform-specific file locations and formats respected

## Technical Architecture

### Core Design Pattern: Strategy Pattern with Platform Abstraction

```
┌─────────────────────────────────────────────┐
│                CLI Interface                 │
│         cidx teach-ai --<platform>           │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│           PlatformFactory                    │
│    Creates platform-specific handlers        │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      AIInstructionHandler (Abstract)         │
│   - get_instruction_content()                │
│   - get_project_file_path()                  │
│   - get_global_file_path()                   │
└────────────────┬────────────────────────────┘
                 │
    ┌────────────┼────────────┬────────────┐
    ▼            ▼            ▼            ▼
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│Claude  │  │Codex   │  │Gemini  │  │Others  │
│Handler │  │Handler │  │Handler │  │Handlers│
└────────┘  └────────┘  └────────┘  └────────┘
    │            │            │            │
    ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────┐
│     Externalized Template Files (.md)       │
│        prompts/ai_instructions/*.md         │
└─────────────────────────────────────────────┘
```

### Command Structure
```
cidx teach-ai --<platform> --<scope> [--show-only]

Platform flags (one required):
  --claude    : Claude Code instructions
  --codex     : GitHub Codex instructions
  --gemini    : Google Gemini instructions
  --opencode  : OpenCode instructions
  --q         : Amazon Q instructions
  --junie     : JetBrains Junie instructions

Scope flags (one required):
  --project   : Create instruction file in project root
  --global    : Create instruction file in platform's global directory

Optional flags:
  --show-only : Display content without writing files
```

### File Management Strategy
- **Project Scope**: PLATFORM.md files in project root
- **Global Scope**: Platform-specific directories (~/.claude/, ~/.codex/, etc.)
- **Template Location**: prompts/ai_instructions/*.md
- **Atomic Writes**: Backup existing files before overwrite
- **Cross-Platform**: Path.home() for compatibility

## Features

### Feature Tracking
- [x] 01_Feat_AIPlatformInstructionResearch
- [x] 02_Feat_ClaudePlatformInstructionManagement
- [x] 03_Feat_MultiPlatformInstructionSupport

### Feature 1: AI Platform Instruction Research
**Priority**: HIGH - Prerequisite for implementation
**Purpose**: Research and document instruction file conventions for all 6 AI platforms
**Deliverable**: Implementation guide with platform-specific requirements

### Feature 2: Claude Platform Instruction Management
**Priority**: HIGH - MVP Core
**Purpose**: Implement teach-ai command for Claude platform with template system
**Deliverable**: Working Claude support with legacy command removal

### Feature 3: Multi-Platform Instruction Support
**Priority**: HIGH - MVP Extension
**Purpose**: Extend teach-ai to support 5 additional AI platforms
**Deliverable**: Complete multi-platform instruction system

## Implementation Order

### Critical Path
```
Story 0.1 (Research)
    ↓
Story 1.1 (Claude Implementation + Legacy Removal)
    ↓
    ├─→ Story 2.1 (Codex & Gemini)
    └─→ Story 2.2 (OpenCode, Q & Junie)
```

### Dependencies
1. **Research First**: Story 0.1 must complete before any implementation
2. **Claude Foundation**: Story 1.1 establishes patterns for other platforms
3. **Parallel Extension**: Stories 2.1 and 2.2 can proceed in parallel

## Success Metrics

### Functional Metrics
- All 6 platforms supported with correct file locations
- Template modification requires zero code changes
- Legacy command fully removed with helpful error message
- Both project and global scopes functional

### Quality Metrics
- Command execution < 500ms
- Template loading < 50ms
- Zero hardcoded instruction content in Python
- 100% atomic file writes with backups

### User Experience Metrics
- Clear error messages for missing flags
- Consistent interface across all platforms
- Preview capability with --show-only
- Comprehensive --help documentation

## Risk Mitigation

### Technical Risks
- **Platform Convention Changes**: Mitigated by external templates
- **File Permission Issues**: Atomic writes with proper error handling
- **Cross-Platform Paths**: Path.home() and pathlib for compatibility

### Implementation Risks
- **Scope Creep**: Fixed platform list, no dynamic loading
- **Template Complexity**: Simple .md files, no templating engine
- **Legacy Migration**: Clear deprecation with helpful error messages

## Testing Strategy

### Manual E2E Testing Matrix
```
6 platforms × 2 scopes = 12 core test cases
+ Template modification tests
+ Error path validation
+ Legacy command removal verification
```

### Unit Testing Focus
- Platform handler factory
- File path resolution
- Template loading
- Flag validation

### Integration Testing
- End-to-end command execution
- File system operations
- Cross-platform compatibility

## Definition of Done

### Epic Completion Criteria
- ✅ All 6 AI platforms have working teach-ai support
- ✅ Templates externalized in prompts/ai_instructions/
- ✅ Legacy "claude" command removed with migration message
- ✅ Both project and global scopes functional
- ✅ All stories passing manual E2E testing
- ✅ Documentation updated (README, --help)
- ✅ fast-automation.sh passing

### Quality Gates
- No hardcoded instruction content in Python code
- All file operations atomic with backup
- Template changes require zero code modifications
- Clear error messages for all failure paths

## Notes

### Legacy Code Removal
- Remove @cli.command("claude") from cli.py:3779-4120
- Replace with helpful migration error message
- Preserve useful patterns from legacy implementation

### Template Management
- Templates are plain .md files (no Jinja2/templating)
- Content focused on cidx semantic search capabilities
- Platform-specific adaptations in separate files

### Platform Expansion
- Architecture supports future platform additions
- New platform = new handler + new template
- No changes to core command structure