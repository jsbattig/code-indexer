# Remove Port Registry Dependency for Filesystem Backend

**Epic**: macOS Compatibility & Container-Free Operation
**Priority**: High (Critical macOS Blocker)
**Status**: Ready for Implementation

---

## Overview

This backlog contains the story to remove the global port registry dependency when using filesystem vector storage, enabling:
- ✅ macOS compatibility for CIDX CLI and daemon
- ✅ Container-free operation (no Docker/Podman needed)
- ✅ No sudo/admin privileges required
- ✅ Simplified setup for filesystem backend users

## The Problem

Currently, `DockerManager` unconditionally initializes `GlobalPortRegistry()` even when using `--vector-store filesystem`:

```python
# src/code_indexer/services/docker_manager.py:36
def __init__(self, ...):
    ...
    self.port_registry = GlobalPortRegistry()  # ❌ ALWAYS runs
```

This causes:
- ❌ Failures on macOS (no `/var/lib/code-indexer/port-registry`)
- ❌ Permission errors on Linux without sudo setup
- ❌ Unnecessary overhead for container-free users

## The Solution

**Lazy Initialization**: Only create GlobalPortRegistry when QdrantContainerBackend is selected.

### Key Implementation Points

1. **QdrantContainerBackend**: Add lazy `docker_manager` and `port_registry` properties
2. **DockerManager**: Make `port_registry` parameter optional, add lazy initialization
3. **CLI Commands**: Add `_needs_docker_manager()` helper to check backend type
4. **Backend Isolation**: Filesystem code path never touches port registry

### Expected Behavior After Fix

```bash
# Filesystem Backend (macOS, Linux, Windows)
cidx init --vector-store filesystem  # ✅ No /var/lib access
cidx index                            # ✅ No port registry
cidx query "auth"                     # ✅ No containers

# Qdrant Backend (Linux with containers)
cidx init --vector-store qdrant       # ✅ Uses port registry as before
cidx start                            # ✅ Containers work as before
```

---

## Stories in This Backlog

### 01_Story_LazyPortRegistryInitialization.md (511 lines)

**Comprehensive Implementation Story**:
- ✅ Detailed acceptance criteria (functional, technical, safety)
- ✅ Phase-by-phase implementation approach (5 phases)
- ✅ Specific code changes with line numbers
- ✅ Test scenarios (unit, integration, manual)
- ✅ File modification list
- ✅ Backward compatibility strategy
- ✅ Error handling specifications

**Key Sections**:
1. **Story Description** - User story, problem statement
2. **Acceptance Criteria** - 20+ checkboxes across 3 categories
3. **Implementation Approach** - 5 detailed phases with code examples
4. **Test Scenarios** - Unit, integration, and manual testing
5. **Files to Modify** - Complete list with line numbers
6. **Definition of Done** - Clear completion criteria

**Estimated Effort**: 2-3 days
**Risk**: Low (well-isolated change)

---

## Related Documentation

### Analysis Reports
- `reports/macos_compatibility_analysis_20251105.md` - Complete macOS compatibility assessment
- Evidence that NO other macOS work is needed besides this story

### Archived Plans (Reference Only)
- `plans/.archived/macos-support-architecture-analysis.md` - Original 3-4 week estimate (OBSOLETE)
- `plans/.archived/epic-eliminate-global-port-registry.md` - Full registry removal (OUT OF SCOPE)

**NOTE**: Original plans were for complete port registry removal and full macOS support. This story is much more focused: just remove the dependency for filesystem backend. That's all that's needed.

---

## Implementation Priority

**Why This is High Priority**:
1. **Blocks macOS users** - Primary blocker for macOS CLI/daemon support
2. **Affects Linux users** - Filesystem backend users shouldn't need sudo
3. **Simple fix** - Well-isolated change, low risk
4. **High impact** - Enables entire new user segment (macOS developers)

**Why NOT to delay**:
- Every day delayed = macOS users can't use CIDX with filesystem backend
- Simple fix with clear implementation path
- No architectural changes needed
- Backward compatible (Qdrant users unaffected)

---

## Testing Strategy

### Pre-Implementation Verification
```bash
# Verify current behavior (FAILS on macOS)
cd ~/test-project
cidx init --vector-store filesystem
# Expected: ❌ Error about /var/lib/code-indexer/port-registry
```

### Post-Implementation Verification
```bash
# Test on macOS
cidx init --vector-store filesystem  # ✅ Should work
cidx index                            # ✅ Should work
cidx query "test"                     # ✅ Should work
cidx config --daemon && cidx start    # ✅ Should work

# Test on Linux (filesystem)
cidx init --vector-store filesystem  # ✅ Should work, no sudo

# Test on Linux (Qdrant - verify no regression)
cidx init --vector-store qdrant      # ✅ Should work as before
cidx setup-global-registry           # ✅ Should work as before
```

---

## Success Criteria

### Functional Success
- [x] Story created with detailed implementation plan
- [ ] Implementation complete with all phases
- [ ] All tests passing (unit, integration, manual)
- [ ] macOS verification successful
- [ ] Qdrant backend regression tests pass

### Business Success
- [ ] macOS users can use CIDX with filesystem backend
- [ ] Linux users don't need sudo for filesystem backend
- [ ] No user complaints about port registry errors
- [ ] Documentation updated with macOS support

---

## Next Steps

1. **Review Story** - Ensure implementation approach is clear
2. **Assign Developer** - Allocate to sprint
3. **Implement** - Follow 5-phase approach in story
4. **Test** - Run all test scenarios
5. **Verify on macOS** - Test with real macOS environment
6. **Deploy** - Ship with next release

---

## Questions?

See the detailed story file for:
- Exact code changes with line numbers
- Complete test scenarios
- Error handling specifications
- Backward compatibility strategy
