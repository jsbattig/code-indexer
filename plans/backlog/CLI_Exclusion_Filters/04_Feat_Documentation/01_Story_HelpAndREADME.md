# Story: Help Text and README Updates

## Summary
Update CLI help text and README documentation to comprehensively document the exclusion filter functionality with practical examples and clear explanations.

**Conversation Context**: "Documentation clearly explains exclusion filter syntax" - Key success criteria from epic

## Description

### User Story
As a developer using CIDX, I want clear documentation and help text that shows me how to use exclusion filters effectively so that I can quickly filter out unwanted files from my searches.

### Technical Context
This story focuses on updating all user-facing documentation to explain the new exclusion filter capabilities, including help text, README examples, and inline documentation.

## Acceptance Criteria

### Help Text Requirements
1. ✅ `cidx query --help` shows exclusion options
2. ✅ Each option has clear description
3. ✅ Examples provided in help text
4. ✅ Common patterns documented
5. ✅ Formatting is consistent

### README Requirements
1. ✅ New "Exclusion Filters" section added
2. ✅ Language exclusion examples
3. ✅ Path exclusion examples
4. ✅ Combined filter examples
5. ✅ Common patterns reference
6. ✅ Performance notes included

## Implementation Details

### 1. CLI Help Text Updates
**File**: `src/code_indexer/cli.py`

```python
@click.command(name="query")
@click.argument('query_text', required=True)
@click.option(
    '--language',
    'languages',
    multiple=True,
    help=(
        'Include only files of specified language(s). '
        'Can be specified multiple times. '
        'Example: --language python --language go'
    )
)
@click.option(
    '--exclude-language',
    'exclude_languages',
    multiple=True,
    help=(
        'Exclude files of specified language(s) from search results. '
        'Can be specified multiple times. '
        'Example: --exclude-language javascript --exclude-language css'
    )
)
@click.option(
    '--path',
    'paths',
    multiple=True,
    help=(
        'Include only files matching the specified path pattern(s). '
        'Uses glob patterns (*, ?, [seq]). '
        'Example: --path "*/src/*" --path "*.py"'
    )
)
@click.option(
    '--exclude-path',
    'exclude_paths',
    multiple=True,
    help=(
        'Exclude files matching the specified path pattern(s) from search results. '
        'Uses glob patterns (*, ?, [seq]). Can be specified multiple times. '
        'Example: --exclude-path "*/tests/*" --exclude-path "*.min.js"'
    )
)
@click.option(
    '--min-score',
    type=float,
    help='Minimum similarity score (0.0-1.0) for results.'
)
@click.option(
    '--limit',
    type=int,
    default=10,
    help='Maximum number of results to return (default: 10).'
)
@click.option(
    '--quiet',
    is_flag=True,
    help='Minimal output mode - only show essential information.'
)
def query(query_text, languages, exclude_languages, paths, exclude_paths, min_score, limit, quiet):
    """
    Perform semantic search on indexed code.

    \b
    Examples:
      # Basic search
      cidx query "database connection"

      # Exclude test files
      cidx query "api endpoint" --exclude-path "*/tests/*"

      # Python only, no tests
      cidx query "authentication" --language python --exclude-path "*/test_*.py"

      # Exclude multiple languages
      cidx query "config" --exclude-language javascript --exclude-language css

      # Complex filtering
      cidx query "database" \\
        --language python \\
        --path "*/src/*" \\
        --exclude-path "*/tests/*" \\
        --exclude-path "*/__pycache__/*" \\
        --min-score 0.7
    """
    # Implementation
```

### 2. README.md Updates
**File**: `README.md`

Add new section after the "Query" section:

```markdown
### Exclusion Filters

CIDX provides powerful exclusion filters to remove unwanted files from your search results. Exclusions always take precedence over inclusions, giving you precise control over your search scope.

#### Excluding Files by Language

Filter out files of specific programming languages using `--exclude-language`:

```bash
# Exclude JavaScript files from results
cidx query "database implementation" --exclude-language javascript

# Exclude multiple languages
cidx query "api handlers" --exclude-language javascript --exclude-language typescript --exclude-language css

# Combine with language inclusion (Python only, no JS)
cidx query "web server" --language python --exclude-language javascript
```

#### Excluding Files by Path Pattern

Use `--exclude-path` with glob patterns to filter out files in specific directories or with certain names:

```bash
# Exclude all test files
cidx query "production code" --exclude-path "*/tests/*" --exclude-path "*_test.py"

# Exclude dependency and cache directories
cidx query "application logic" \
  --exclude-path "*/node_modules/*" \
  --exclude-path "*/vendor/*" \
  --exclude-path "*/__pycache__/*"

# Exclude by file extension
cidx query "source code" --exclude-path "*.min.js" --exclude-path "*.pyc"

# Complex path patterns
cidx query "configuration" --exclude-path "*/build/*" --exclude-path "*/.*" # Hidden files
```

#### Combining Multiple Filter Types

Create sophisticated queries by combining inclusion and exclusion filters:

```bash
# Python files in src/, excluding tests and cache
cidx query "database models" \
  --language python \
  --path "*/src/*" \
  --exclude-path "*/tests/*" \
  --exclude-path "*/__pycache__/*"

# High-relevance results, no test files or vendored code
cidx query "authentication logic" \
  --min-score 0.8 \
  --exclude-path "*/tests/*" \
  --exclude-path "*/vendor/*" \
  --exclude-language javascript

# API code only, multiple exclusions
cidx query "REST endpoints" \
  --path "*/api/*" \
  --exclude-path "*/tests/*" \
  --exclude-path "*/mocks/*" \
  --exclude-language javascript \
  --exclude-language css
```

#### Common Exclusion Patterns

##### Testing Files
```bash
--exclude-path "*/tests/*"        # Test directories
--exclude-path "*/test/*"         # Alternative test dirs
--exclude-path "*_test.py"        # Python test files
--exclude-path "*_test.go"        # Go test files
--exclude-path "*.test.js"        # JavaScript test files
--exclude-path "*/fixtures/*"     # Test fixtures
--exclude-path "*/mocks/*"        # Mock files
```

##### Dependencies and Vendor Code
```bash
--exclude-path "*/node_modules/*" # Node.js dependencies
--exclude-path "*/vendor/*"       # Vendor libraries
--exclude-path "*/.venv/*"        # Python virtual environments
--exclude-path "*/site-packages/*" # Python packages
--exclude-path "*/bower_components/*" # Bower dependencies
```

##### Build Artifacts and Cache
```bash
--exclude-path "*/build/*"        # Build output
--exclude-path "*/dist/*"         # Distribution files
--exclude-path "*/target/*"       # Maven/Cargo output
--exclude-path "*/__pycache__/*"  # Python cache
--exclude-path "*.pyc"            # Python compiled files
--exclude-path "*.pyo"            # Python optimized files
--exclude-path "*.class"          # Java compiled files
--exclude-path "*.o"              # Object files
--exclude-path "*.so"             # Shared libraries
```

##### Generated and Minified Files
```bash
--exclude-path "*.min.js"         # Minified JavaScript
--exclude-path "*.min.css"        # Minified CSS
--exclude-path "*_pb2.py"         # Protocol buffer generated
--exclude-path "*.generated.*"    # Generated files
--exclude-path "*/migrations/*"   # Database migrations
```

#### Performance Notes

- Each exclusion filter adds minimal overhead (typically <2ms)
- Filters are applied during the search phase, not during indexing
- Use specific patterns when possible for better performance
- Complex glob patterns may have slightly higher overhead
- The order of filters does not affect performance
```

### 3. Error Message Improvements

Add helpful error messages throughout the implementation:

```python
# Unknown language warning
if unknown_languages:
    console.print(
        f"[yellow]Warning: Unknown language(s): {', '.join(unknown_languages)}\n"
        f"Supported languages: {', '.join(sorted(LANGUAGE_MAPPER.keys()))}[/yellow]"
    )

# Conflicting filters warning
if conflicts:
    console.print(
        f"[yellow]Warning: Language '{lang}' is both included and excluded. "
        f"Exclusion takes precedence - this language will be filtered out.[/yellow]"
    )

# Invalid pattern warning
if invalid_pattern:
    console.print(
        f"[red]Error: Invalid path pattern '{pattern}'. "
        f"Please use valid glob syntax (*, ?, [seq], [!seq]).[/red]"
    )

# No results due to filters
if not results and (exclude_languages or exclude_paths):
    console.print(
        "[yellow]No results found. Your exclusion filters may be too restrictive. "
        "Try relaxing some filters.[/yellow]"
    )
```

## Testing Documentation

### Test All Examples
Create a script to test all documentation examples:

```python
# tests/test_documentation_examples.py
def test_all_readme_examples():
    """Verify all README examples work correctly."""
    examples = [
        'cidx query "database" --exclude-language javascript',
        'cidx query "api" --exclude-path "*/tests/*"',
        # ... all examples from README
    ]
    for example in examples:
        # Run and verify no errors
        result = run_command(example)
        assert result.returncode == 0
```

## Validation Checklist

- [ ] Help text is clear and accurate
- [ ] Examples in help text work
- [ ] README section is comprehensive
- [ ] All examples are tested
- [ ] Common patterns documented
- [ ] Error messages are helpful
- [ ] Performance notes included
- [ ] Formatting is consistent

## Definition of Done

- [ ] CLI help text updated with examples
- [ ] README.md updated with new section
- [ ] All examples manually tested
- [ ] Error messages implemented
- [ ] Documentation reviewed for clarity
- [ ] Spell check and grammar check done
- [ ] Code comments added where needed
- [ ] PR description references this story