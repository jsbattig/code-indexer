# Query Parameter Inventory

## Purpose

This document serves as the authoritative reference for all query parameters supported by CIDX across all interfaces (CLI, REST API, MCP API). It ensures parameter consistency and prevents future parity regressions.

## Overview

CIDX currently supports **23 query parameters** across three interfaces:

- **CLI**: 18 parameters (subset - some API-only temporal params not exposed)
- **REST API**: 23 parameters (full set)
- **MCP API**: 23 parameters (full set)

## Complete Parameter List

### Core Parameters

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| query | string | QUERY (positional) | query_text | query_text | (required) | Search query text | Initial |
| limit | integer | --limit | limit | limit | 10 | Maximum number of results (1-100) | Initial |
| min_score | float | --min-score | min_score | min_score | 0.5 | Minimum similarity score (0.0-1.0) | Initial |

### Language and Path Filtering

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| language | string | --language | language | language | None | Filter by programming language (python, javascript, etc.) | Initial |
| path_filter | string | --path-filter | path_filter | path_filter | None | Filter by path pattern (glob syntax: */tests/*, **/*.py) | Initial |
| exclude_language | string | --exclude-language | exclude_language | exclude_language | None | Exclude files of specified language | Phase 1 |
| exclude_path | string | --exclude-path | exclude_path | exclude_path | None | Exclude files matching path pattern (glob syntax) | Phase 1 |
| file_extensions | array | N/A | file_extensions | file_extensions | None | Filter by file extensions ([".py", ".js"]) - API-only | Initial |

### Search Mode Selection

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| search_mode | enum | --fts / --semantic | search_mode | search_mode | semantic | Search mode: semantic, fts, or hybrid | Initial |

### Search Accuracy

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| accuracy | enum | --accuracy | accuracy | accuracy | balanced | Search accuracy profile: fast, balanced, high | Phase 1 |

### FTS-Specific Parameters

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| case_sensitive | boolean | --case-sensitive | case_sensitive | case_sensitive | false | Enable case-sensitive FTS matching | Phase 2 |
| fuzzy | boolean | --fuzzy | fuzzy | fuzzy | false | Enable fuzzy matching with edit distance 1 | Phase 2 |
| edit_distance | integer | --edit-distance | edit_distance | edit_distance | 0 | Fuzzy match tolerance (0=exact, 1-3=typos allowed) | Phase 2 |
| snippet_lines | integer | --snippet-lines | snippet_lines | snippet_lines | 5 | Context lines around FTS matches (0-50) | Phase 2 |
| regex | boolean | --regex | regex | regex | false | Interpret query as regex pattern (FTS-only) | Phase 1 |

### Temporal Query Parameters

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| time_range | string | --time-range | time_range | time_range | None | Time range filter (YYYY-MM-DD..YYYY-MM-DD) | Story #446 |
| at_commit | string | N/A | at_commit | at_commit | None | Query code at specific commit hash or ref - API-only | Story #446 |
| include_removed | boolean | N/A | include_removed | include_removed | false | Include removed files in results - API-only | Story #446 |
| show_evolution | boolean | N/A | show_evolution | show_evolution | false | Show code evolution timeline - API-only | Story #446 |
| evolution_limit | integer | N/A | evolution_limit | evolution_limit | None | Limit evolution entries (user-controlled) - API-only | Story #446 |

### Temporal Filtering Parameters

| Parameter | Type | CLI Flag | REST Field | MCP Field | Default | Description | Phase |
|-----------|------|----------|------------|-----------|---------|-------------|-------|
| diff_type | string/array | --diff-type | diff_type | diff_type | None | Filter by diff type (added/modified/deleted/renamed/binary) | Phase 3 |
| author | string | --author | author | author | None | Filter by commit author (name or email) | Phase 3 |
| chunk_type | enum | --chunk-type | chunk_type | chunk_type | None | Filter by chunk type: commit_message or commit_diff | Phase 3 |

## Parameter Naming Conventions

### CLI-Specific Naming

- **Positional argument**: `QUERY` (required first argument, not a flag)
- **Hyphenated flags**: `--exclude-language`, `--path-filter`, `--min-score`
- **Search mode flags**: `--fts` and `--semantic` (instead of `--search-mode` enum)
- **Temporal shortcut**: `--time-range-all` (shortcut for full temporal range)
- **Case sensitivity**: `--case-insensitive` (inverse flag available)

### REST/MCP API Naming

- **Underscore notation**: `query_text`, `min_score`, `exclude_language`
- **Enum field**: `search_mode` (values: `semantic`, `fts`, `hybrid`)
- **Boolean fields**: `case_sensitive`, `fuzzy`, `regex`, `include_removed`, `show_evolution`

## API-Only Parameters

The following parameters are **NOT exposed in CLI** (only available via REST/MCP):

1. **at_commit**: Query code at specific commit hash - API provides more flexibility
2. **include_removed**: Include removed files - API-specific feature
3. **show_evolution**: Code evolution timeline - API-specific feature
4. **evolution_limit**: Control evolution entry count - API-specific feature
5. **file_extensions**: Array-based extension filtering - API uses this, CLI uses --language

## Validation Rules

### Parameter Constraints

- **limit**: 1-100 (REST/MCP enforce maximum 100)
- **min_score**: 0.0-1.0 (similarity score threshold)
- **edit_distance**: 0-3 (fuzzy matching tolerance)
- **snippet_lines**: 0-50 (FTS context lines)
- **accuracy**: Enum values: `fast`, `balanced`, `high`
- **search_mode**: Enum values: `semantic`, `fts`, `hybrid`
- **chunk_type**: Enum values: `commit_message`, `commit_diff`

### Parameter Conflicts

- **regex + fuzzy**: Mutually exclusive (CLI/API validation enforces this)
- **FTS parameters**: Only applicable when `search_mode` is `fts` or `hybrid`
- **Temporal parameters**: Require temporal index built with `cidx index --index-commits`

## Parity Enforcement

Automated tests in `tests/unit/query/test_query_parameter_parity.py` enforce:

1. All 23 parameters exist in REST and MCP APIs
2. CLI has expected 18 parameters (excludes API-only temporal params)
3. No unexpected parameters are added without updating this document
4. Parameter names are consistent between REST and MCP
5. Parameter types are compatible across interfaces
6. Default values are consistent between REST and MCP

## Implementation Reference

### CLI Implementation

- **File**: `src/code_indexer/cli.py`
- **Command**: `cidx query`
- **Help**: Run `cidx query --help` to see all CLI parameters

### REST API Implementation

- **File**: `src/code_indexer/server/app.py`
- **Model**: `SemanticQueryRequest` (Pydantic)
- **Endpoint**: `POST /api/v1/query`

### MCP API Implementation

- **File**: `src/code_indexer/server/mcp/tools.py`
- **Tool**: `search_code`
- **Schema**: JSON Schema in `TOOL_REGISTRY["search_code"]["inputSchema"]`

## Phase History

### Initial Implementation
Core parameters: query, limit, min_score, language, path_filter, search_mode, file_extensions

### Story #503 Phase 1 (P0 Gaps - REST API)
Added: exclude_language, exclude_path, accuracy, regex

### Story #503 Phase 2 (P1 Gaps - MCP FTS Options)
Added: case_sensitive, fuzzy, edit_distance, snippet_lines

### Story #503 Phase 3 (P1 Gaps - Temporal Filtering)
Added: diff_type, author, chunk_type

### Story #446 (Temporal Query Parameters)
Added: time_range, at_commit, include_removed, show_evolution, evolution_limit

### Story #503 Phase 4 (Documentation & Validation)
Created this inventory document and automated parity validation tests

## Future Additions

When adding new query parameters:

1. Add parameter to **all three interfaces** (CLI, REST, MCP) unless there's a strong reason it's API-only
2. Update **this document** with parameter details (type, default, description, phase)
3. Update **automated parity tests** in `test_query_parameter_parity.py`
4. Update **CLI help text** (via @click.option decorator)
5. Update **OpenAPI schema** (via SemanticQueryRequest Pydantic model)
6. Update **MCP schema** (via TOOL_REGISTRY in tools.py)
7. Update **README.md** with usage examples

## Version History

- **v7.4.0**: Phase 4 implementation - Parameter inventory documentation and automated parity validation tests
- **v7.3.0**: Phase 3 implementation - Temporal filtering parameters (diff_type, author, chunk_type)
- **v7.2.0**: Phase 2 implementation - MCP FTS options (case_sensitive, fuzzy, edit_distance, snippet_lines)
- **v7.1.0**: Phase 1 implementation - REST API P0 gaps (exclude_language, exclude_path, accuracy, regex)
- **v7.0.0**: Temporal query parameters (time_range, at_commit, include_removed, show_evolution, evolution_limit)
