# CIDX Repository Topology Architecture

## Overview

CIDX uses a three-tier repository topology to support multi-user code indexing with CoW (Copy-on-Write) cloning efficiency. This document defines the canonical repository structure and resolution rules.

## Three-Tier Architecture

### 1. Golden Repositories (Source of Truth)

**Purpose**: Direct clones from GitHub/GitLab serving as authoritative sources

**Location**: `{data_dir}/golden-repos/{alias}/`

**Example**: `/home/user/.cidx-server/data/golden-repos/my-project/`

**Characteristics**:
- Direct git clone from remote repository
- Single remote: `origin` pointing to GitHub/GitLab URL
- Updated via `git pull` or `cidx refresh`
- Serves as CoW clone source for activated repos
- Metadata stored in `{data_dir}/golden-repos/metadata.json`

**Creation**:
```python
# GoldenRepoManager.register_golden_repo()
clone_path = os.path.join(self.golden_repos_dir, alias)
git clone {repo_url} {clone_path}
```

### 2. Global Repositories (Indexed, Queryable)

**Purpose**: Versioned, indexed snapshots for multi-user semantic search

**Location**: `{data_dir}/golden-repos/.versioned/{repo}/v_{timestamp}/`

**Example**: `/home/user/.cidx-server/data/golden-repos/.versioned/my-project/v_1735516800/`

**Characteristics**:
- Timestamped snapshots of golden repos
- Semantic + FTS indexes generated
- SCIP call graphs (if supported language)
- Multiple versions coexist (temporal queries)
- Alias naming: `{repo-name}-global`
- Registry stored in `{data_dir}/golden-repos/global_registry.json`

**Creation**:
```python
# GlobalActivator.activate_golden_repo()
versioned_path = f"{golden_repos_dir}/.versioned/{alias}/v_{timestamp}/"
# CoW clone from golden repo
# Generate indexes (semantic + FTS + SCIP)
```

### 3. Activated Repositories (User Workspaces)

**Purpose**: Per-user isolated working copies for editing and committing

**Location**: `{data_dir}/activated-repos/{username}/{user_alias}/`

**Example**: `/home/user/.cidx-server/data/activated-repos/alice/my-project-feature/`

**Characteristics**:
- CoW cloned from golden repos (fast, space-efficient)
- Dual remote model (Story #636):
  - `origin`: GitHub/GitLab URL (for push/pull)
  - `golden`: Local golden repo path (for sync)
- Per-user isolation (no cross-user interference)
- Metadata stored in `{user_dir}/{user_alias}_metadata.json`

**Creation**:
```python
# ActivatedRepoManager.activate_repository()
repo_path = f"{activated_repos_dir}/{username}/{user_alias}/"
# CoW clone from golden repo
# Setup dual remotes (origin + golden)
```

## Mixed Topology Models

### Historical Context

CIDX currently supports TWO storage models due to evolutionary architecture:

**Flat Structure (Legacy)**:
- Golden repos at: `/golden-repos/{alias}/`
- No versioning
- Direct filesystem access

**Versioned Structure (Current)**:
- Global repos at: `/golden-repos/.versioned/{repo}/v_{timestamp}/`
- Temporal indexing
- Snapshot isolation

### Current State

**Flat Structure Repos** (13 repos):
- Created before versioned storage implementation
- Stored directly in `golden-repos/{alias}/`
- Metadata `clone_path` matches actual filesystem location
- No global indexing (golden-only)

**Versioned Structure Repos** (12 repos):
- Created with global activation enabled
- Stored in `.versioned/{repo}/v_{timestamp}/`
- Metadata `clone_path` points to flat structure (STALE)
- Global indexes available

### Path Resolution (Canonical)

**Problem**: Metadata often stores stale flat structure paths while repos exist in versioned structure.

**Solution**: `GoldenRepoManager.get_actual_repo_path(alias)` performs canonical resolution:

```python
def get_actual_repo_path(self, alias: str) -> str:
    """
    Resolve actual filesystem path for golden/global repo.

    Priority order:
    1. Check metadata clone_path exists → return if found
    2. Check .versioned/{alias}/v_*/ → return latest if found
    3. Raise GoldenRepoNotFoundError

    Security: Validates paths stay within golden_repos_dir sandbox.
    """
```

**Usage**:
- Migration code (Story #636)
- Git operations requiring golden repo access
- Global registry path lookups
- Any code trusting metadata paths

## Migration Path (Future)

### Option A: Standardize on Versioned Structure

**Pros**:
- Temporal queries across all repos
- Consistent architecture
- Snapshot isolation

**Cons**:
- Migration complexity for 13 flat repos
- Storage overhead for versions
- Breaking change for existing code

### Option B: Support Both Models Indefinitely

**Pros**:
- No migration needed
- Backward compatibility maintained
- Canonical resolution handles both

**Cons**:
- Architectural inconsistency
- Two code paths to maintain
- Confusion about which model to use

### Recommendation

**Current approach (Option B)** is correct for now:
- Canonical path resolution accommodates both models
- No forced migration required
- New repos default to versioned structure
- Legacy flat repos continue working

**Future evolution** (when ready):
- Migrate flat repos to versioned (one-time operation)
- Deprecate flat structure code paths
- Update all metadata to point to versioned paths
- Simplify to single model

## Security Invariants

### Sandbox Enforcement

All repositories MUST reside within `{data_dir}/golden-repos/` directory:

**Allowed**:
```
/data/golden-repos/my-repo/              # Flat structure
/data/golden-repos/.versioned/my-repo/   # Versioned structure
```

**Forbidden**:
```
/data/other-location/my-repo/            # Outside sandbox
/data/golden-repos/../etc/passwd         # Path traversal
```

**Validation**:
```python
# Input validation (reject dangerous characters)
if ".." in alias or "/" in alias or "\\" in alias:
    raise ValueError("Path traversal detected")

# Realpath verification (prevent symlink attacks)
resolved = os.path.realpath(path)
if not resolved.startswith(os.path.realpath(golden_repos_dir)):
    raise ValueError("Security violation: path escapes sandbox")
```

### Attack Prevention

**Path Traversal**: Input validation rejects `..`, `/`, `\` in alias
**Symlink Attacks**: Realpath verification ensures paths stay within sandbox
**Malformed Input**: Graceful handling of invalid version directories

## API Compatibility

### Metadata Files

**Golden Repos** (`metadata.json`):
```json
{
  "repo-alias": {
    "alias": "repo-alias",
    "repo_url": "git@github.com:user/repo.git",
    "clone_path": "/data/golden-repos/repo-alias",  // May be stale
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

**Global Repos** (`global_registry.json`):
```json
{
  "repo-alias-global": {
    "repo_name": "repo-alias",
    "alias_name": "repo-alias-global",
    "repo_url": "git@github.com:user/repo.git",
    "index_path": "/data/golden-repos/repo-alias",  // May be stale
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

**Activated Repos** (`{user_alias}_metadata.json`):
```json
{
  "user_alias": "my-workspace",
  "golden_repo_alias": "repo-alias",
  "current_branch": "main",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Path Resolution Contract

**Old Behavior** (before canonical resolution):
```python
# Direct metadata access (WRONG - may be stale)
golden_repo_path = golden_repo.clone_path
```

**New Behavior** (canonical resolution):
```python
# Validated filesystem lookup (CORRECT)
golden_repo_path = golden_repo_manager.get_actual_repo_path(alias)
```

## Testing Guidelines

### Test Fixture Architecture

All test repositories MUST respect sandbox boundaries:

**Correct**:
```python
golden_repos_dir = os.path.join(temp_dir, "golden-repos")
test_repo = os.path.join(golden_repos_dir, "test-repo")  # Inside sandbox
```

**Incorrect**:
```python
test_repo = os.path.join(temp_dir, "test-repo")  # Outside sandbox
# Security validation will reject this
```

### Integration Tests

When testing repository operations:
- Create repos inside `golden-repos/` directory
- Use canonical path resolution for lookups
- Verify paths stay within sandbox
- Test both flat and versioned structures

## References

- **Story #636**: Dual remote model for activated repositories
- **Issue #639**: Bug fixes for path resolution and migration
- **Topology Bugs Document**: `/tmp/topology-bugs.md`
- **Implementation**: `src/code_indexer/server/repositories/golden_repo_manager.py`
