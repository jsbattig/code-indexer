# Feature: AI Platform Instruction Research

## Feature Overview

### Purpose
Research and document instruction file conventions for all 6 AI coding platforms to enable accurate implementation of platform-specific instruction generation.

### Business Value
- **Accurate Implementation**: Eliminates guesswork about platform conventions
- **Reduced Rework**: Prevents trial-and-error implementation approaches
- **Platform Compliance**: Ensures generated files match platform expectations
- **Developer Efficiency**: Provides clear implementation guide for all stories

### Success Criteria
- ✅ All 6 platforms researched with documented conventions
- ✅ Global directory locations identified per platform
- ✅ File naming conventions documented
- ✅ Format requirements specified (markdown, JSON, YAML)
- ✅ Implementation guide created with comparison table

## Stories

### Story Tracking
- [ ] 01_Story_MultiPlatformInstructionConventionResearch

## Technical Approach

### Research Methodology
```
For Each Platform:
├── Official Documentation Review
│   ├── Search platform documentation
│   ├── Find instruction file specifications
│   └── Document official conventions
│
├── Empirical Testing
│   ├── Examine existing installations
│   ├── Test file locations and formats
│   └── Verify AI agent recognition
│
└── Community Resources
    ├── GitHub examples
    ├── Forum discussions
    └── Best practices
```

### Platforms to Research

#### Claude Code (Anthropic)
- Global directory location
- File naming (CLAUDE.md expected)
- Format requirements
- Instruction syntax

#### GitHub Codex
- Global configuration path
- File naming convention
- Format (markdown, JSON, or YAML)
- Specific requirements

#### Google Gemini
- Global settings location
- Instruction file format
- Naming conventions
- Integration approach

#### OpenCode
- Configuration directory
- File format requirements
- Naming standards
- Platform-specific needs

#### Amazon Q
- Enterprise configuration
- File location requirements
- Format specifications
- Security considerations

#### JetBrains Junie
- IDE integration path
- Configuration format
- File naming rules
- JetBrains conventions

## Deliverables

### Implementation Guide Structure
```
1. Executive Summary
   - Quick reference table
   - Key findings

2. Platform-by-Platform Details
   - Claude Code
   - GitHub Codex
   - Google Gemini
   - OpenCode
   - Amazon Q
   - JetBrains Junie

3. Comparison Matrix
   - File locations
   - Naming conventions
   - Format requirements
   - Special considerations

4. Implementation Recommendations
   - Common patterns
   - Platform-specific handlers
   - Error handling approaches
```

### Documentation Format
```markdown
## Platform: [Name]

### Global Directory
- Primary: ~/.platform/
- Alternative: ~/Library/Application Support/Platform/
- Windows: %APPDATA%\Platform\

### File Naming
- Convention: PLATFORM.md or .platform.json
- Case sensitivity: Yes/No

### Format Requirements
- Type: Markdown/JSON/YAML
- Encoding: UTF-8
- Line endings: LF/CRLF

### Example Structure
[Code block with example]

### Special Considerations
- [Platform-specific requirements]
```

## Dependencies

### Upstream Dependencies
- None (first feature in epic)

### Downstream Impact
- Story 1.1 depends on Claude research findings
- Story 2.1 depends on Codex/Gemini findings
- Story 2.2 depends on OpenCode/Q/Junie findings

## Validation Approach

### Research Validation
1. **Documentation Cross-Check**: Verify against official docs
2. **Practical Testing**: Create sample files and test recognition
3. **Community Validation**: Check against existing implementations
4. **Version Compatibility**: Note any version-specific differences

### Quality Criteria
- Each platform has complete documentation
- File locations tested on actual systems
- Format requirements validated
- Edge cases identified

## Risk Management

### Research Risks
- **Limited Documentation**: Some platforms may lack clear specs
  - Mitigation: Empirical testing and community resources

- **Platform Updates**: Conventions may change
  - Mitigation: Document version tested, design for flexibility

- **Access Limitations**: May not have all platforms available
  - Mitigation: Use web research and community examples

## Definition of Done

### Feature Completion Criteria
- ✅ All 6 platforms researched
- ✅ Implementation guide document created
- ✅ Comparison matrix completed
- ✅ File location specifications documented
- ✅ Format requirements identified
- ✅ Example structures provided
- ✅ Guide reviewed for accuracy

### Quality Gates
- Documentation is clear and actionable
- Each platform has testable specifications
- Implementation recommendations are specific
- Guide enables confident implementation