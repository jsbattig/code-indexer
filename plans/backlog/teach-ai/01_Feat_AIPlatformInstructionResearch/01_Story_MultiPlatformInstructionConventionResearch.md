# Story: Multi-Platform Instruction Convention Research

## Story Overview

### User Story
As a developer implementing the teach-ai feature, I want to research how each AI coding platform (Claude Code, Codex, Gemini, OpenCode, Q, Junie) expects to receive instruction files so that I can design accurate platform-specific instruction generation.

### Value Delivered
Working research documentation that enables accurate implementation of platform-specific instruction generation without guesswork or trial-and-error.

### Story Points Indicators
- 🔍 Research-heavy story (no code implementation)
- 📊 6 platforms to investigate
- 📁 Deliverable is documentation, not code

## Acceptance Criteria (Gherkin)

```gherkin
Feature: Multi-Platform Instruction Convention Research

Scenario: Research platform instruction conventions
  Given I need to implement teach-ai for 6 AI platforms
  When I research each platform's instruction file conventions
  Then I document the following for each platform:
    | Aspect                      | Required Information                          |
    | Global directory location   | ~/.claude/, ~/.codex/, etc.                 |
    | File naming convention      | CLAUDE.md, .codex.json, etc.                |
    | Format requirements         | Markdown, JSON, YAML                        |
    | Platform-specific syntax    | Special conventions or requirements          |
    | Example files              | From official documentation                  |

Scenario: Compile research into implementation guide
  Given the research is complete
  When I compile the findings into an implementation guide
  Then the guide contains:
    | Section                    | Content                                       |
    | Comparison table          | Platform-by-platform feature matrix           |
    | File specifications       | Exact paths and naming for each platform      |
    | Format requirements       | Detailed format specs per platform            |
    | Example structures        | Sample instruction files                      |
    | Recommendations          | Implementation approach suggestions            |

Scenario: Enable accurate implementation
  Given the implementation guide is created
  When other stories reference platform-specific conventions
  Then developers have authoritative source for accurate implementation
  And no guesswork is required for file locations or formats
```

## Research Tasks

### Task Checklist
- [ ] Research Claude Code instruction conventions
- [ ] Research GitHub Codex instruction conventions
- [ ] Research Google Gemini instruction conventions
- [ ] Research OpenCode instruction conventions
- [ ] Research Amazon Q instruction conventions
- [ ] Research JetBrains Junie instruction conventions
- [ ] Create comparison matrix
- [ ] Document implementation recommendations
- [ ] Validate findings with practical testing

### Platform Research Template

For each platform, document:

```markdown
## [Platform Name]

### 1. Official Documentation
- Documentation URL:
- Version researched:
- Date researched:

### 2. Global Configuration
- Primary location:
- Fallback locations:
- Cross-platform paths:

### 3. File Conventions
- File name:
- Extension:
- Case sensitivity:

### 4. Format Specifications
- Format type:
- Schema/Structure:
- Required fields:
- Optional fields:

### 5. Example Content
[Example instruction file content]

### 6. Special Considerations
- Platform-specific requirements:
- Version differences:
- Known limitations:

### 7. Testing Results
- File location verified:
- Format verified:
- Agent recognition tested:
```

## Research Sources

### Primary Sources
1. **Official Documentation**
   - Platform developer documentation
   - API documentation
   - Configuration guides

2. **Empirical Testing**
   - Actual platform installations
   - File system examination
   - Agent behavior testing

3. **Community Resources**
   - GitHub repositories using the platforms
   - Stack Overflow discussions
   - Developer forums and blogs

### Research Queries

#### Web Search Queries
- "[Platform] instruction file location"
- "[Platform] configuration directory"
- "[Platform] custom instructions"
- "[Platform] .md file configuration"
- "[Platform] AI agent setup"

#### File System Exploration
```pseudocode
Common locations to check:
- ~/.platform/
- ~/Library/Application Support/Platform/
- ~/.config/platform/
- ~/.local/share/platform/
- %APPDATA%\Platform\ (Windows)
```

## Deliverable Structure

### Implementation Guide Outline

```
# AI Platform Instruction Conventions - Implementation Guide

## Executive Summary
- Quick reference table
- Key findings and patterns

## Platform Specifications

### Claude Code
- Global: ~/.claude/CLAUDE.md
- Project: ./CLAUDE.md
- Format: Markdown
- [Details...]

### GitHub Codex
- Global: [Research finding]
- Project: [Research finding]
- Format: [Research finding]
- [Details...]

### Google Gemini
- Global: [Research finding]
- Project: [Research finding]
- Format: [Research finding]
- [Details...]

### OpenCode
- Global: [Research finding]
- Project: [Research finding]
- Format: [Research finding]
- [Details...]

### Amazon Q
- Global: [Research finding]
- Project: [Research finding]
- Format: [Research finding]
- [Details...]

### JetBrains Junie
- Global: [Research finding]
- Project: [Research finding]
- Format: [Research finding]
- [Details...]

## Comparison Matrix
| Platform | Global Dir | File Name | Format | Special Requirements |
|----------|------------|-----------|--------|---------------------|
| Claude   | ~/.claude/ | CLAUDE.md | MD     | None               |
| ...      | ...        | ...       | ...    | ...                 |

## Implementation Recommendations
1. Use strategy pattern for platform handlers
2. Externalize templates for maintainability
3. [Additional recommendations...]

## Appendices
- Sample instruction files
- Test results
- Version compatibility notes
```

## Manual Testing

### Testing Approach
1. **Setup Test Environment**
   - Install available AI platforms
   - Create test projects

2. **Location Testing**
   - Create instruction files in researched locations
   - Verify AI agents detect and use them
   - Test both global and project scopes

3. **Format Testing**
   - Test different format variations
   - Verify which formats are recognized
   - Document any format restrictions

4. **Content Testing**
   - Test instruction content effectiveness
   - Verify agents follow provided instructions
   - Document any content limitations

### Validation Checklist
- [ ] Claude Code file location confirmed
- [ ] GitHub Codex file location confirmed
- [ ] Google Gemini file location confirmed
- [ ] OpenCode file location confirmed
- [ ] Amazon Q file location confirmed
- [ ] JetBrains Junie file location confirmed
- [ ] All format requirements documented
- [ ] Example files created and tested
- [ ] Cross-platform paths verified

## Definition of Done

### Story Completion Criteria
- ✅ All 6 platforms researched thoroughly
- ✅ Implementation guide document created
- ✅ Comparison matrix completed with all platforms
- ✅ File locations tested where possible
- ✅ Format requirements clearly documented
- ✅ Example instruction files provided
- ✅ Implementation recommendations written
- ✅ Guide enables confident implementation of other stories

### Quality Gates
- Research covers both global and project scopes
- Documentation is specific and actionable
- File paths are absolute and tested
- Format specifications are unambiguous
- Guide answers all implementation questions