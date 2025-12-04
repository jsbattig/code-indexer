# MCP Tool Documentation Improvement Plan

## Executive Summary

This plan addresses documentation discoverability issues identified in user feedback. The goal is to achieve **flawless discovery** - users should instantly know which tool to use for any task.

## Key Insight: Tool Hierarchy

CIDX tools form a clear hierarchy based on **indexing** and **purpose**:

### Tier 1: Pre-Indexed Search (FAST - Use First)
These tools use pre-built indexes for instant results:
- **search_code (semantic)** - Conceptual/meaning-based search. NOT text-based. Approximates relevant code areas given a topic. Results are NOT exhaustive but help quickly identify areas of concern.
- **search_code (fts)** - Full-text search with index. Fast exact text/identifier matching.
- **search_code (temporal)** - Search code through git history. Requires temporal index.

### Tier 2: Direct Exploration (COMPREHENSIVE - Deep Dive)
These tools work directly on filesystem/git without indexes:
- **regex_search** - Pattern matching directly on files (grep-like)
- **git_* tools** - Git archaeology (log, blame, diff, history)
- **browse_directory, directory_tree** - File system exploration
- **get_file_content** - Read specific files

### Tier 3: Repository Management
- **list_global_repos, add_golden_repo, refresh_golden_repo** - Manage indexed repos
- **activate_repository, deactivate_repository** - Branch-specific access
- **global_repo_status, get_repository_status** - Status and health

---

## Implementation Plan

### P0: Tool Discovery Index (Highest Impact)

Add a prominent discovery guide to the MCP tool listing that appears FIRST when tools are listed.

**Content Structure:**

```
# CIDX Code Search Tools - Quick Reference

## How Do I...

### Find Code by Concept/Meaning
search_code(query="authentication logic", search_mode="semantic")
- Semantic search finds code by meaning, not exact text
- IMPORTANT: Results are approximate, not exhaustive
- Best for: "Where is X implemented?", "Code that does Y"

### Find Exact Text/Identifiers
search_code(query="def authenticate_user", search_mode="fts")
- Full-text search with index (fast)
- Best for: Function names, class names, variable names

### Find Code Pattern (Regex)
regex_search(repo_identifier="myrepo-global", pattern="TODO.*fix")
- Direct regex search on files (no index, comprehensive)
- Best for: Pattern matching, syntax searching

### Explore Git History
git_log → Recent commits
git_file_history → Single file's commit history
git_blame → Who wrote each line
git_diff → Changes between versions
git_search_commits → Find commits by message
git_search_diffs → Find when code was added/removed (pickaxe)

### Navigate Codebase
directory_tree → Visual file hierarchy
browse_directory → File list with metadata
get_file_content → Read file contents

### Manage Repositories
list_global_repos → Available searchable repos
add_golden_repo → Register new repo for indexing
global_repo_status → Check repo health/features
```

### P1: Standardize Tool Descriptions

Apply consistent pattern to ALL tools:

**Template:**
```
## [Tool Name]

**TL;DR:** [1-sentence purpose]

**Quick Start:**
[Most common usage example]

**When to Use:**
- [Scenario 1]
- [Scenario 2]

**When NOT to Use:**
- [Anti-pattern] → Use [alternative] instead

**Related Tools:**
- [tool] - [relationship]
```

### P2: Decision Trees

#### Search Tool Decision Tree
```
Q: What are you searching for?
├─ Concept/meaning ("authentication logic")
│  → search_code(search_mode="semantic")
│  Note: Approximate results, not exhaustive
│
├─ Exact text/identifier ("authenticate_user")
│  → search_code(search_mode="fts")
│  Alternative: regex_search for no-index search
│
├─ Pattern/regex ("def.*auth")
│  → regex_search (comprehensive, slower)
│  → search_code(search_mode="fts", regex=true) (indexed)
│
├─ Code through history ("what did auth look like in 2023")
│  → search_code with time_range (requires temporal index)
│
└─ Not sure?
   → search_code(search_mode="hybrid")
```

#### Git Tool Decision Tree
```
Q: What git info do you need?
├─ Recent commits in repo
│  → git_log
│
├─ History of specific file
│  → git_file_history
│  Alt: git_log(path="file.py")
│
├─ Who wrote this code?
│  → git_blame
│
├─ What changed between versions?
│  → git_diff
│
├─ Find commits by message
│  → git_search_commits
│
├─ When was code added/removed?
│  → git_search_diffs (pickaxe)
│
├─ View file at past version
│  → git_file_at_revision
│
└─ Full commit details
   → git_show_commit
```

### P3: Critical Clarifications

#### Semantic Search is NOT Text Search
```
IMPORTANT: Semantic search finds code by MEANING, not exact text.

What it DOES:
- Finds conceptually related code
- Helps identify areas of concern for a topic
- Works even when naming differs from query

What it does NOT do:
- Return exhaustive/complete results
- Find exact text matches
- Guarantee all relevant code is found

For exact text: Use FTS mode or regex_search
```

#### Pickaxe Search Explained
```
"Pickaxe" is git's term for finding commits where text was added/removed.

Unlike git_search_commits (searches commit messages),
git_search_diffs searches the actual CODE CHANGES.

Use case: "When was DEALER_INITIATED_LEAD added to the codebase?"
```

---

## Tools to Update

### High Priority (User-Facing Search)
1. search_code - Add TL;DR, clarify semantic vs FTS vs hybrid
2. regex_search - Add comparison with search_code
3. list_global_repos - Add as discovery starting point

### Medium Priority (Git Tools)
4. git_log - Add "When to Use" / "When NOT to Use"
5. git_file_history - Add comparison with git_log(path=)
6. git_blame - Clear use case
7. git_diff - Clarify comparison scenarios
8. git_search_commits - Clarify vs git_search_diffs
9. git_search_diffs - Explain pickaxe, add timing warning
10. git_file_at_revision - Clear use case
11. git_show_commit - Clear use case

### Medium Priority (Browse Tools)
12. directory_tree - Clarify vs browse_directory
13. browse_directory - Clarify vs directory_tree
14. get_file_content - Simple, clear purpose

### Lower Priority (Admin Tools)
15-35. Repository management, user management, health checks

---

## Implementation Approach

1. Create a new "discovery guide" tool description that appears first
2. Update search_code with TL;DR and clearer mode explanations
3. Update all git tools with "When to Use" / "When NOT to Use"
4. Add "Related Tools" sections to all tools
5. Test via MCP client to verify discoverability

---

## Success Metrics

- Users can find the right tool within 30 seconds
- Zero confusion between semantic vs FTS search
- Clear understanding that semantic search is approximate
- Git tool selection is obvious from decision tree
- 9/10 documentation rating (up from 7.5/10)

---

## Estimated Effort

- P0 (Discovery Index): 1 hour
- P1 (Standardize descriptions): 2-3 hours
- P2 (Decision trees embedded): 30 min
- P3 (Clarifications): 30 min

Total: 4-5 hours
