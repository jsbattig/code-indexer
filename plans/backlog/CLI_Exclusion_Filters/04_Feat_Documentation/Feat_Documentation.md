# Feature: Documentation

## Overview

This feature provides comprehensive documentation for the exclusion filter functionality, including help text updates, README examples, and usage guidelines. Clear documentation is critical for user adoption and proper usage.

**Conversation Context**: "Documentation clearly explains exclusion filter syntax" - Success criteria from epic requirements

## Business Value

### Problem Statement
Without clear documentation, users won't discover or properly use the exclusion filter features, limiting their effectiveness and causing frustration with incorrect usage.

### Expected Outcome
Users can quickly understand and effectively use exclusion filters through clear help text, comprehensive README examples, and intuitive error messages.

## Functional Requirements

### Documentation Components
1. **CLI Help Text**: Update `--help` output with exclusion examples
2. **README Updates**: Add exclusion filter section with examples
3. **Error Messages**: Clear feedback for invalid inputs
4. **Usage Examples**: Common patterns and use cases
5. **Performance Notes**: Impact of complex filters

### Help Text Updates
```bash
$ cidx query --help
Usage: cidx query [OPTIONS] QUERY

  Perform semantic search on indexed code.

Options:
  --language TEXT         Include only files of specified language(s).
                         Can be specified multiple times.
                         Example: --language python --language go

  --exclude-language TEXT Exclude files of specified language(s).
                         Can be specified multiple times.
                         Example: --exclude-language javascript --exclude-language css

  --path TEXT            Include only files matching path pattern(s).
                         Uses glob patterns (*, ?, [seq]).
                         Example: --path "*/src/*"

  --exclude-path TEXT    Exclude files matching path pattern(s).
                         Uses glob patterns (*, ?, [seq]).
                         Can be specified multiple times.
                         Example: --exclude-path "*/tests/*" --exclude-path "*.min.js"

  --min-score FLOAT      Minimum similarity score (0.0-1.0)
  --limit INTEGER        Maximum number of results (default: 10)
  --quiet               Minimal output mode
  --help                Show this message and exit.

Examples:
  # Exclude test files from search
  cidx query "database connection" --exclude-path "*/tests/*"

  # Search only Python files, excluding tests
  cidx query "api endpoint" --language python --exclude-path "*/test_*.py"

  # Exclude multiple languages
  cidx query "configuration" --exclude-language javascript --exclude-language css

  # Complex filtering
  cidx query "authentication" \
    --language python \
    --path "*/src/*" \
    --exclude-path "*/tests/*" \
    --exclude-path "*/__pycache__/*" \
    --min-score 0.7
```

## Documentation Structure

### README.md Section
```markdown
## Exclusion Filters

CIDX supports excluding files from search results using language and path filters. Exclusions take precedence over inclusions, allowing precise control over search scope.

### Excluding by Language

Use `--exclude-language` to filter out files of specific programming languages:

```bash
# Exclude JavaScript files
cidx query "database implementation" --exclude-language javascript

# Exclude multiple languages
cidx query "api" --exclude-language javascript --exclude-language typescript --exclude-language css
```

### Excluding by Path Pattern

Use `--exclude-path` with glob patterns to exclude files matching specific paths:

```bash
# Exclude test directories
cidx query "production code" --exclude-path "*/tests/*"

# Exclude multiple patterns
cidx query "source code" --exclude-path "*/tests/*" --exclude-path "*/vendor/*" --exclude-path "*/__pycache__/*"

# Exclude by file extension
cidx query "code" --exclude-path "*.min.js" --exclude-path "*.pyc"
```

### Combining Filters

Combine inclusion and exclusion filters for precise searches:

```bash
# Python files only, excluding tests
cidx query "database" --language python --exclude-path "*/tests/*"

# Source directory only, excluding vendor and tests
cidx query "api" --path "*/src/*" --exclude-path "*/vendor/*" --exclude-path "*/tests/*"
```

### Common Patterns

#### Exclude Test Files
```bash
--exclude-path "*/tests/*" --exclude-path "*/test_*.py" --exclude-path "*_test.go"
```

#### Exclude Dependencies
```bash
--exclude-path "*/node_modules/*" --exclude-path "*/vendor/*" --exclude-path "*/.venv/*"
```

#### Exclude Build Artifacts
```bash
--exclude-path "*/build/*" --exclude-path "*/dist/*" --exclude-path "*.pyc" --exclude-path "*.o"
```

#### Exclude Generated Files
```bash
--exclude-path "*.min.js" --exclude-path "*.min.css" --exclude-path "*_pb2.py"
```

### Performance Considerations

- Each filter adds minimal overhead (<2ms per filter)
- Complex patterns may slightly impact performance
- Exclusions are processed after inclusions
- Use specific patterns when possible for best performance
```

## Acceptance Criteria

### Documentation Requirements
1. ✅ CLI help text includes exclusion options
2. ✅ Examples show common use cases
3. ✅ README has dedicated exclusion section
4. ✅ Pattern syntax is explained
5. ✅ Performance impact is documented
6. ✅ Error messages are helpful

### Quality Criteria
1. ✅ Documentation is clear and concise
2. ✅ Examples are practical and tested
3. ✅ Common patterns are provided
4. ✅ Edge cases are mentioned
5. ✅ Precedence rules are explained

## Implementation Notes

### Files to Update
1. **CLI Help**: `src/code_indexer/cli.py` - Option descriptions
2. **README**: `README.md` - New section for exclusions
3. **Error Messages**: Throughout implementation
4. **Code Comments**: Document complex logic

### Documentation Principles
- **Show, don't just tell**: Provide working examples
- **Common first**: Document common use cases prominently
- **Progressive disclosure**: Basic usage first, advanced later
- **Practical examples**: Real-world scenarios

## Test Requirements

### Documentation Tests
1. **Help text accuracy**: Verify examples work
2. **README examples**: Test all documented commands
3. **Error message clarity**: User testing feedback
4. **Pattern examples**: Validate all patterns work

## Conversation References

- **Documentation Requirement**: "Documentation clearly explains exclusion filter syntax"
- **Help Text Examples**: Show common patterns from conversation
- **README Update**: Part of success criteria

## Definition of Done

- [ ] CLI help text updated
- [ ] README section added
- [ ] All examples tested
- [ ] Error messages improved
- [ ] Pattern reference included
- [ ] Performance notes added
- [ ] Documentation reviewed
- [ ] User feedback incorporated