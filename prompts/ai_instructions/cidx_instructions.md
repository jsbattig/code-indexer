## SEMANTIC SEARCH - MANDATORY FIRST ACTION

**CIDX FIRST**: Always use `cidx query` before grep/find/rg for semantic searches.

**Decision Rule**:
- "What code does", "Do we support", "Where is X implemented" → CIDX semantic (default)
- Exact text (function names, class names, identifiers) → CIDX with `--fts`
- Pattern matching (regex) → CIDX with `--fts --regex` (10-50x faster than grep on indexed repos)
- Single-file text search when CIDX unavailable → grep/find (last resort only)

**Key Parameters**: `--limit N` (results, default 10) | `--language python` (filter by language) | `--path-filter */tests/*` (filter by path pattern) | `--min-score 0.8` (similarity threshold) | `--accuracy high` (higher precision) | `--quiet` (minimal output)

**Examples**: `cidx query "authentication login" --quiet` | `cidx query "error handling" --language python --limit 20` | `cidx query "database connection" --path-filter */services/* --min-score 0.8`

**Exclusion Filters**: `--exclude-language LANG` | `--exclude-path PATTERN`

**Common**: Tests `--exclude-path "*/tests/*"` | Deps `--exclude-path "*/node_modules/*"` | Build `--exclude-path "*/build/*"` | Generated `--exclude-path "*.min.js"`

**Examples**: `cidx query "production code" --exclude-path "*/tests/*" --exclude-language javascript` | `cidx query "api logic" --path-filter */src/* --exclude-path "*/mocks/*" --exclude-language css`

## FULL-TEXT SEARCH - EXACT MATCHING

**When to Use FTS**: Exact function/class names, identifiers, TODO comments, typo debugging.

**FTS Flags**: `--fts` (enable FTS) | `--case-sensitive` (exact case) | `--fuzzy` (1-char tolerance) | `--edit-distance N` (0-3, typo tolerance) | `--snippet-lines N` (0-50, context lines)

**FTS Filters** (same as semantic): `--language LANG` | `--exclude-language LANG` | `--path-filter PATTERN` | `--exclude-path PATTERN` | Multiple allowed for each | Precedence: language exclude → language include → path exclude → path include

**Examples**:
- Find exact function: `cidx query "authenticate_user" --fts --quiet`
- Case-sensitive class: `cidx query "UserAuth" --fts --case-sensitive --quiet`
- Fuzzy typo search: `cidx query "athenticate" --fts --fuzzy --quiet`
- TODO comments: `cidx query "TODO" --fts --snippet-lines 0 --quiet`
- Filter by language: `cidx query "parse" --fts --language python --quiet`
- Exclude tests: `cidx query "config" --fts --exclude-path "*/tests/*" --quiet`
- Combined filters: `cidx query "auth" --fts --language python --path-filter "*/src/*" --exclude-path "*/legacy/*" --quiet`

**Hybrid Search** (both semantic + FTS): `--fts --semantic` runs both in parallel

**Example**: `cidx query "parse" --fts --semantic --limit 5 --quiet`

## REGEX PATTERN MATCHING - GREP REPLACEMENT

**USE INSTEAD OF GREP**: `cidx query --fts --regex` is 10-50x faster than grep on indexed repos and supports all filters.

**Regex Flags**: `--regex` (enable token-based regex) | Incompatible with `--semantic` and `--fuzzy`

**Token-Based Limitation**: Tantivy regex matches individual TOKENS, not full text:
- ✅ Works: `r"def"`, `r"login.*"`, `r"test_.*"`, `r"TODO"`
- ❌ Doesn't work: `r"def\s+\w+"` (whitespace removed in tokenization)

**Examples** (ALWAYS use `--quiet` for conciseness):
- Function defs: `cidx query "def" --fts --regex --language python --quiet`
- Auth patterns: `cidx query "auth.*" --fts --regex --exclude-path "*/tests/*" --quiet`
- Test functions: `cidx query "test_.*" --fts --regex --quiet`
- TODO comments: `cidx query "todo" --fts --regex --quiet` (lowercase)
- Error constants: `cidx query "ERROR.*" --fts --regex --case-sensitive --quiet`
- URL patterns: `cidx query "https.*" --fts --regex --language markdown --quiet`

**Grep Replacement Examples**:
- Instead of: `grep -r "function\s\+\w\+" . --include="*.js"` → `cidx query "function" --fts --regex --language javascript --quiet`
- Instead of: `grep -i "TODO" . -r` → `cidx query "todo" --fts --regex --quiet`
- Instead of: `find . -name "*.py" -exec grep "def.*auth" {} +` → `cidx query "def.*auth" --fts --regex --language python --quiet`

**Fallback**: Use grep/find only when CIDX unavailable or for single-file searches.
