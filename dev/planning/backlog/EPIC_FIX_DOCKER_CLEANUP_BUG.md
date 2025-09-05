# EPIC: Fix Docker Container Cleanup Bug in Uninstall Command

## Epic Intent

**Fix critical bug where `cidx uninstall --force-docker` leaves dangling Docker containers that prevent subsequent startup operations, causing name conflicts and requiring manual cleanup.**

## Problem Statement

The `cidx uninstall` command fails to completely remove Docker containers, particularly those in "Created" or "Exited" states, leading to:

### Critical Issues Observed
- **Container Name Conflicts**: Subsequent `cidx start` operations fail with "container name already exists" errors
- **Manual Cleanup Required**: Users must run `docker container prune -f` and manually remove specific containers
- **Production Blocking**: Complete project reinstallation becomes impossible without manual Docker intervention
- **Inconsistent State**: Some containers left in "Created" state (never started) block name reuse

### Evidence from Production
```bash
docker ps -a | grep cidx
# Shows dangling containers:
a6dd3ed605ce   tries-qdrant                    ./entrypoint.sh   1 min ago   Created   cidx-7068eeed-qdrant
2dd725084f79   cidx-data-cleaner               /cleanup.sh       8 min ago   Exited(137)  cidx-7068eeed-data-cleaner
```

### Root Cause Analysis
1. **Container Naming Mismatch**: Cleanup verification uses wrong naming pattern (`{project_name}-{service}-1` vs `cidx-{project_hash}-{service}`)
2. **Incomplete Compose Cleanup**: `docker-compose down` doesn't handle containers created outside compose context
3. **Missing Force Cleanup**: Force container removal only runs on graceful stop failure, not compose down failure
4. **State-Agnostic Logic**: No special handling for "Created" state containers that block name reuse

## Technical Architecture

### Current Cleanup Flow (BROKEN)
```
cidx uninstall --force-docker
├── DockerManager.cleanup(remove_data=True)
├── stop_main_services() [BROKEN: wrong container names]
├── docker-compose down -v [INCOMPLETE: misses orphaned containers]
├── _force_cleanup_containers() [CONDITIONAL: only on graceful stop failure]
└── Result: Dangling containers remain
```

### Required Fix Architecture
```
cidx uninstall --force-docker
├── DockerManager.cleanup(remove_data=True)
├── stop_main_services() [FIXED: correct container names]  
├── docker-compose down -v --remove-orphans
├── _force_cleanup_containers() [MANDATORY: always run for uninstall]
├── _cleanup_created_state_containers() [NEW: handle Created state]
└── Result: Complete container removal guaranteed
```

### Component Specifications

#### 1. **Container Name Resolution Fix**
- **File**: `src/code_indexer/services/docker_manager.py:4290`
- **Issue**: Uses `f"{self.project_name}-{service}-1"` instead of project-specific names
- **Fix**: Use `self.get_container_name(service, project_config)` for accurate naming

#### 2. **Mandatory Force Cleanup**
- **File**: `src/code_indexer/services/docker_manager.py:3066`
- **Issue**: Force cleanup only runs conditionally on graceful stop failure
- **Fix**: Always run force cleanup for `remove_data=True` operations (uninstall)

#### 3. **Enhanced Container State Handling**  
- **File**: `src/code_indexer/services/docker_manager.py:3212-3286`
- **Issue**: Doesn't specifically target "Created" state containers
- **Fix**: Remove containers regardless of state with comprehensive error handling

#### 4. **Compose Down Enhancement**
- **File**: `src/code_indexer/services/docker_manager.py:3072-3082`
- **Issue**: Missing `--remove-orphans` flag for uninstall operations
- **Fix**: Add orphan removal for complete cleanup

## User Stories

### Story 1: Fix Container Name Resolution in Stop Services
**As a developer running cidx uninstall, I want the stop services operation to use correct container names so that containers are properly identified and stopped before removal.**

**Acceptance Criteria:**
- Given I have project-specific containers with names like `cidx-{hash}-qdrant`
- When the system attempts to stop services during uninstall
- Then `stop_main_services()` uses `self.get_container_name(service, project_config)` for accurate naming
- And container verification checks succeed with correct names
- And all containers are properly stopped before removal attempts
- And no containers remain running due to name mismatches

**Implementation Details:**
```python
# In stop_main_services() around line 4290
# OLD (BROKEN):
container_name = f"{self.project_name}-{service}-1"

# NEW (FIXED):  
container_name = self.get_container_name(service, project_config_dict)
```

### Story 2: Implement Mandatory Force Cleanup for Uninstall Operations
**As a developer running cidx uninstall, I want force cleanup to always run during uninstall operations so that no containers are left behind regardless of compose down success.**

**Acceptance Criteria:**
- Given I run `cidx uninstall --force-docker` with `remove_data=True`
- When the cleanup process executes
- Then force cleanup runs regardless of docker-compose down results
- And all cidx containers are removed using direct Docker commands
- And the system handles containers in any state (Created, Running, Exited, Paused)
- And no manual cleanup is required after uninstall completion

**Implementation Algorithm:**
```python
def cleanup(self, remove_data: bool = False, force: bool = False, verbose: bool = False):
    # ... existing logic ...
    
    # Run compose down
    result = subprocess.run(down_cmd, ...)
    
    # MANDATORY: Always force cleanup for uninstall (remove_data=True)
    if remove_data:
        if verbose:
            self.console.print("🔧 Running mandatory force cleanup for uninstall...")
        cleanup_success &= self._force_cleanup_containers(verbose)
    
    # ... rest of cleanup logic ...
```

### Story 3: Enhance Force Cleanup to Handle All Container States
**As a system maintaining Docker containers, I want force cleanup to remove containers in any state so that name conflicts never occur after uninstall.**

**Acceptance Criteria:**
- Given containers exist in "Created", "Exited", "Running", or any other state
- When `_force_cleanup_containers()` executes
- Then all cidx containers are removed regardless of their current state
- And "Created" state containers (never started) are properly removed
- And containers with exit codes (like 137) are properly removed
- And no container states are left that could block future name reuse
- And comprehensive error handling prevents partial cleanup failures

**Enhanced Cleanup Algorithm:**
```python
def _force_cleanup_containers(self, verbose: bool = False) -> bool:
    # Find ALL cidx containers in ANY state
    list_cmd = [container_engine, "ps", "-a", "--format", "{{.Names}}", "--filter", "name=cidx-"]
    
    for container_name in container_names:
        try:
            # Always attempt to kill first (handles Running state)
            subprocess.run([container_engine, "kill", container_name], 
                         capture_output=True, timeout=10)
            
            # Force remove regardless of kill result (handles all states)
            rm_result = subprocess.run(
                [container_engine, "rm", "-f", container_name],
                capture_output=True, text=True, timeout=10
            )
            
            if rm_result.returncode == 0:
                if verbose:
                    self.console.print(f"✅ Removed container: {container_name}")
            else:
                if verbose:
                    self.console.print(f"⚠️  Container removal warning: {rm_result.stderr}")
                    
        except Exception as e:
            success = False
            if verbose:
                self.console.print(f"❌ Failed to remove {container_name}: {e}")
```

### Story 4: Add Orphan Container Removal to Compose Down
**As a developer running uninstall, I want docker-compose down to remove orphaned containers so that containers created outside compose context are properly cleaned up.**

**Acceptance Criteria:**
- Given containers may exist that were created outside the compose context
- When `docker-compose down` runs during uninstall
- Then the `--remove-orphans` flag is included for uninstall operations
- And orphaned containers are removed along with compose-managed containers
- And the cleanup process is more comprehensive than standard compose down
- And no additional manual steps are required for orphan removal

**Implementation Details:**
```python
# In cleanup() method around line 3082
down_cmd = compose_cmd + ["-f", str(self.compose_file), "-p", self.project_name, "down"]
if remove_data:
    down_cmd.extend(["-v", "--remove-orphans"])  # Add orphan removal for uninstall
if force:
    down_cmd.extend(["--timeout", "10"])
```

### Story 5: Create Comprehensive Cleanup Validation
**As a developer, I want the cleanup process to validate complete container removal so that uninstall success is guaranteed and verifiable.**

**Acceptance Criteria:**
- Given cleanup operations have completed
- When cleanup validation runs
- Then no cidx containers remain in Docker (any state)
- And validation provides clear success/failure feedback
- And any remaining containers are explicitly reported with details
- And the system provides specific guidance if manual cleanup is still needed
- And validation covers all container engines (docker/podman)

**Validation Algorithm:**
```python
def _validate_complete_cleanup(self, verbose: bool = False) -> bool:
    container_engine = self._get_available_runtime()
    
    # Check for ANY remaining cidx containers
    list_cmd = [container_engine, "ps", "-a", "--format", "{{.Names}}\t{{.State}}", "--filter", "name=cidx-"]
    result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=10)
    
    if result.returncode == 0 and result.stdout.strip():
        remaining_containers = result.stdout.strip().split('\n')
        if verbose:
            self.console.print("❌ Remaining containers found after cleanup:")
            for container in remaining_containers:
                name, state = container.split('\t')
                self.console.print(f"  - {name} (state: {state})")
        return False
    
    if verbose:
        self.console.print("✅ Complete cleanup validation passed - no containers remain")
    return True
```

### Story 6: Implement Comprehensive Error Reporting
**As a developer debugging cleanup issues, I want detailed error reporting during uninstall so that I can identify and resolve any remaining issues.**

**Acceptance Criteria:**
- Given cleanup operations may encounter various failure modes
- When verbose mode is enabled during uninstall
- Then all cleanup steps report detailed success/failure status
- And specific container names and states are reported during operations
- And Docker command outputs are captured and reported on failures
- And final validation provides comprehensive status of cleanup results
- And actionable guidance is provided if manual cleanup is still required

## Technical Implementation Requirements

### Thread Safety Considerations
- All container operations must be atomic to prevent race conditions
- Multiple cleanup attempts should not interfere with each other
- Container listing and removal operations should be properly serialized

### Error Handling Requirements
- Continue cleanup attempts even if individual containers fail to remove
- Collect and report all errors at the end of the process
- Provide specific error codes for different failure types
- Never leave the system in a partially cleaned state

### Performance Requirements  
- Complete cleanup should finish within 60 seconds under normal conditions
- Force cleanup should have appropriate timeouts (10s per container)
- Validation should complete quickly (5s) for immediate feedback
- No excessive Docker API calls that could cause rate limiting

### Compatibility Requirements
- Must work with both Docker and Podman engines
- Must handle both compose-managed and manually created containers
- Must work across different Docker versions and configurations
- Must maintain backward compatibility with existing uninstall behavior

## Testing Strategy

### Unit Tests Required
- `test_stop_main_services_correct_naming()` - Verify container name resolution fix
- `test_force_cleanup_mandatory_for_uninstall()` - Verify force cleanup always runs
- `test_force_cleanup_handles_all_states()` - Test Created, Exited, Running states
- `test_compose_down_removes_orphans()` - Verify orphan removal
- `test_cleanup_validation_comprehensive()` - Test validation catches remaining containers

### Integration Tests Required  
- `test_complete_uninstall_workflow()` - Full uninstall with container verification
- `test_uninstall_with_failed_containers()` - Handle containers that fail to start
- `test_uninstall_with_created_state_containers()` - Specific test for Created state issue
- `test_multiple_project_cleanup()` - Ensure project isolation during cleanup

### Manual Testing Protocol
```bash
# Test Case 1: Clean uninstall after normal operation
cd test_project_1
cidx init --embedding-provider ollama
cidx start
cidx index
cidx uninstall --force-docker
# Verify: docker ps -a | grep cidx (should show nothing)

# Test Case 2: Uninstall after startup failure (reproduces original bug)  
cd test_project_2
cidx init --embedding-provider ollama
# Simulate startup failure by stopping Docker service briefly
cidx start  # This should fail and leave containers in "Created" state
cidx uninstall --force-docker
# Verify: docker ps -a | grep cidx (should show nothing)

# Test Case 3: Uninstall with mixed container states
cd test_project_3
cidx init --embedding-provider ollama
cidx start
docker kill cidx-{hash}-qdrant  # Force one container to exit
cidx uninstall --force-docker
# Verify: docker ps -a | grep cidx (should show nothing)
```

## Definition of Done

### Functional Requirements
- [ ] `cidx uninstall --force-docker` removes ALL cidx containers regardless of state
- [ ] No manual Docker cleanup required after uninstall
- [ ] Container name resolution uses correct project-specific naming
- [ ] Force cleanup runs mandatory for all uninstall operations
- [ ] Compose down includes `--remove-orphans` for complete cleanup
- [ ] Comprehensive validation confirms complete container removal

### Quality Requirements  
- [ ] All unit tests pass with 100% coverage of modified code
- [ ] Integration tests validate complete workflows
- [ ] Manual testing confirms bug reproduction and fix
- [ ] Error handling provides clear, actionable feedback
- [ ] Performance meets specified timeout requirements
- [ ] Both Docker and Podman engines supported

### Production Readiness
- [ ] No breaking changes to existing uninstall behavior
- [ ] Backward compatibility maintained for existing projects  
- [ ] Comprehensive error logging for debugging
- [ ] Clear success/failure indicators for users
- [ ] Documentation updated with new cleanup behavior

## Risk Assessment

### High Risk Items
- **Container Engine Compatibility**: Different behavior between Docker/Podman versions
- **Race Conditions**: Multiple cleanup operations running simultaneously
- **Permission Issues**: Container removal requiring elevated privileges

### Mitigation Strategies
- **Extensive Testing**: Cover all supported container engines and versions
- **Atomic Operations**: Ensure container operations are properly serialized
- **Graceful Degradation**: Provide clear error messages when manual cleanup is needed
- **Rollback Strategy**: Maintain existing cleanup behavior as fallback

## Success Metrics

### Before Fix (Current Broken State)
- **Manual Cleanup Required**: 100% of failed startup scenarios require manual cleanup
- **Container Conflicts**: Name conflicts block 100% of subsequent startups after failed uninstall
- **User Experience**: Negative - requires Docker expertise for basic operation

### After Fix (Target State)
- **Automatic Cleanup**: 100% of uninstall operations complete without manual intervention
- **Container Conflicts**: 0% name conflicts after successful uninstall
- **User Experience**: Seamless - uninstall "just works" as expected
- **Error Recovery**: Clear error messages and guidance for edge cases

This epic addresses a critical production bug that significantly impacts user experience and system reliability. The fix ensures robust, complete cleanup that eliminates the need for manual Docker intervention.

## Manual End-to-End Test Plan

### Test Environment Setup

**Prerequisites:**
- Docker or Podman installed and running
- Code-indexer with the bug fix implemented
- Access to `/tmp` directory for test operations
- Ability to run Docker commands with appropriate permissions
- Terminal with ability to run multiple test sessions

**Initial Setup Steps:**
1. Ensure no existing cidx containers are running:
   ```bash
   docker ps -a | grep cidx  # Should show no results
   # If containers exist, clean them:
   docker ps -a --format "{{.Names}}" | grep cidx | xargs -r docker rm -f
   ```

2. Create test directories:
   ```bash
   mkdir -p /tmp/cidx-test-{1,2,3,4,5}
   ```

3. Verify Docker/Podman availability:
   ```bash
   docker version || podman version
   ```

### Test Case 1: Normal Operation with Clean Uninstall

**Objective:** Verify that uninstall completely removes all containers after normal successful operation.

**Test Setup:**
```bash
cd /tmp/cidx-test-1
rm -rf .cidx  # Clean any previous config
```

**Execution Steps:**
1. Initialize project with ollama:
   ```bash
   cidx init --embedding-provider ollama --segment-size 512
   ```
   
2. Start all services:
   ```bash
   cidx start
   ```
   
3. Verify containers are running:
   ```bash
   docker ps | grep cidx
   # Expected: Should see cidx-*-qdrant, cidx-*-ollama, cidx-*-data-cleaner containers
   ```
   
4. Perform basic indexing operation:
   ```bash
   echo "test file content" > test.txt
   cidx index
   ```
   
5. Verify services are operational:
   ```bash
   cidx status
   # Expected: All services should show as running
   ```
   
6. Execute uninstall with force-docker flag:
   ```bash
   cidx uninstall --force-docker
   ```

**Verification Steps:**
1. Check for any remaining containers:
   ```bash
   docker ps -a | grep cidx
   # Expected: No output - all containers removed
   ```
   
2. Verify container names are available for reuse:
   ```bash
   docker ps -a --format "{{.Names}}" | grep "cidx-"
   # Expected: No output
   ```
   
3. Check Docker system for orphaned resources:
   ```bash
   docker system df
   # Note: No cidx-related containers should appear
   ```

**Success Criteria:**
- ✅ All cidx containers completely removed
- ✅ No containers in any state (Running, Exited, Created)
- ✅ Container names available for reuse
- ✅ No manual cleanup required

**Cleanup:**
```bash
cd /
rm -rf /tmp/cidx-test-1
```

### Test Case 2: Uninstall After Startup Failure (Original Bug Reproduction)

**Objective:** Reproduce the original bug scenario where startup failures leave containers in "Created" state and verify the fix handles this correctly.

**Test Setup:**
```bash
cd /tmp/cidx-test-2
rm -rf .cidx
```

**Execution Steps:**
1. Initialize project:
   ```bash
   cidx init --embedding-provider ollama --segment-size 256
   ```
   
2. Simulate startup failure by creating a port conflict:
   ```bash
   # Start a dummy container on the Qdrant port to force failure
   docker run -d --name port-blocker -p 6333:80 nginx:alpine
   cidx start
   # Expected: Startup should fail with port conflict
   ```
   
3. Remove the port blocker:
   ```bash
   docker rm -f port-blocker
   ```
   
4. Check container states:
   ```bash
   docker ps -a | grep cidx
   # Expected: Some containers in "Created" or "Exited" state
   ```
   
5. Document problematic containers:
   ```bash
   docker ps -a --format "table {{.Names}}\t{{.State}}\t{{.Status}}" | grep cidx
   # Record the output for verification
   ```
   
6. Execute uninstall:
   ```bash
   cidx uninstall --force-docker --verbose
   # Note: Use verbose to see detailed cleanup operations
   ```

**Verification Steps:**
1. Verify complete removal:
   ```bash
   docker ps -a | grep cidx
   # Expected: No output
   ```
   
2. Attempt to start fresh to verify name availability:
   ```bash
   cidx init --embedding-provider ollama
   cidx start
   # Expected: Should start successfully without name conflicts
   cidx stop
   cidx uninstall --force-docker
   ```

**Success Criteria:**
- ✅ Containers in "Created" state are removed
- ✅ Containers in "Exited" state are removed  
- ✅ No "container name already exists" errors on subsequent start
- ✅ Verbose output shows force cleanup execution

**Cleanup:**
```bash
cd /
rm -rf /tmp/cidx-test-2
```

### Test Case 3: Mixed Container States Cleanup

**Objective:** Test cleanup when containers are in various states (Running, Stopped, Created, Paused).

**Test Setup:**
```bash
cd /tmp/cidx-test-3
rm -rf .cidx
```

**Execution Steps:**
1. Initialize and start:
   ```bash
   cidx init --embedding-provider ollama
   cidx start
   ```
   
2. Create mixed container states:
   ```bash
   # Get container names
   CONTAINERS=$(docker ps --format "{{.Names}}" | grep cidx)
   
   # Kill one container (creates Exited state)
   docker kill $(echo $CONTAINERS | awk '{print $1}')
   
   # Stop another gracefully (creates Exited with code 0)
   docker stop $(echo $CONTAINERS | awk '{print $2}')
   
   # If possible, pause one (creates Paused state)
   docker pause $(echo $CONTAINERS | awk '{print $3}') 2>/dev/null || true
   ```
   
3. Document container states:
   ```bash
   docker ps -a --format "table {{.Names}}\t{{.State}}\t{{.Status}}" | grep cidx
   # Expected: Mix of Running, Exited, possibly Paused states
   ```
   
4. Execute uninstall:
   ```bash
   cidx uninstall --force-docker --verbose
   ```

**Verification Steps:**
1. Verify all states cleaned:
   ```bash
   docker ps -a --format "{{.Names}}\t{{.State}}" | grep cidx
   # Expected: No output
   ```
   
2. Check for orphaned volumes:
   ```bash
   docker volume ls | grep cidx
   # Expected: No cidx volumes remain
   ```

**Success Criteria:**
- ✅ Running containers stopped and removed
- ✅ Exited containers removed (both graceful and forced)
- ✅ Paused containers unpaused and removed
- ✅ All container states handled correctly

**Cleanup:**
```bash
cd /
rm -rf /tmp/cidx-test-3
```

### Test Case 4: Rapid Sequential Install/Uninstall Cycles

**Objective:** Verify cleanup reliability under rapid cycling to detect race conditions or incomplete cleanup.

**Test Setup:**
```bash
cd /tmp/cidx-test-4
rm -rf .cidx
```

**Execution Steps:**
1. Run multiple rapid cycles:
   ```bash
   for i in {1..3}; do
     echo "=== Cycle $i ==="
     
     # Initialize
     cidx init --embedding-provider ollama --segment-size 512
     
     # Start services
     cidx start
     
     # Quick verification
     docker ps | grep cidx | wc -l
     echo "Running containers: $(docker ps | grep cidx | wc -l)"
     
     # Immediate uninstall
     cidx uninstall --force-docker
     
     # Verify cleanup
     REMAINING=$(docker ps -a | grep cidx | wc -l)
     echo "Remaining containers after uninstall: $REMAINING"
     
     if [ $REMAINING -ne 0 ]; then
       echo "ERROR: Containers remain after cycle $i"
       docker ps -a | grep cidx
       exit 1
     fi
     
     sleep 2  # Brief pause between cycles
   done
   ```

**Verification Steps:**
1. Final verification:
   ```bash
   docker ps -a | grep cidx
   # Expected: No containers
   ```
   
2. Check system resources:
   ```bash
   docker system df
   # Verify no accumulation of cidx resources
   ```

**Success Criteria:**
- ✅ All cycles complete successfully
- ✅ No container accumulation between cycles
- ✅ Each cycle starts fresh without conflicts
- ✅ No resource leaks detected

**Cleanup:**
```bash
cd /
rm -rf /tmp/cidx-test-4
```

### Test Case 5: Force Cleanup with Network/Volume Dependencies

**Objective:** Test cleanup when containers have network and volume dependencies.

**Test Setup:**
```bash
cd /tmp/cidx-test-5
rm -rf .cidx
```

**Execution Steps:**
1. Initialize with data operations:
   ```bash
   cidx init --embedding-provider ollama
   cidx start
   ```
   
2. Create data to establish volume usage:
   ```bash
   # Index some files to create vector data
   echo "test content 1" > file1.txt
   echo "test content 2" > file2.txt
   cidx index
   ```
   
3. Verify volumes in use:
   ```bash
   docker volume ls | grep cidx
   # Document volume names
   ```
   
4. Check network configuration:
   ```bash
   docker network ls | grep cidx
   # Document network names
   ```
   
5. Force uninstall:
   ```bash
   cidx uninstall --force-docker --verbose
   ```

**Verification Steps:**
1. Verify container cleanup:
   ```bash
   docker ps -a | grep cidx
   # Expected: No containers
   ```
   
2. Verify volume cleanup:
   ```bash
   docker volume ls | grep cidx
   # Expected: Volumes removed with --remove-data flag
   ```
   
3. Verify network cleanup:
   ```bash
   docker network ls | grep cidx
   # Expected: Custom networks removed
   ```

**Success Criteria:**
- ✅ Containers removed despite volume dependencies
- ✅ Volumes cleaned up with remove_data option
- ✅ Networks properly cleaned up
- ✅ No dangling resources

**Cleanup:**
```bash
cd /
rm -rf /tmp/cidx-test-5
```

### Test Case 6: Docker vs Podman Engine Compatibility

**Objective:** Verify cleanup works correctly with both Docker and Podman engines.

**Test Setup:**
```bash
# This test requires both engines available
# Skip if only one engine is present
docker version >/dev/null 2>&1 && DOCKER_AVAILABLE=true || DOCKER_AVAILABLE=false
podman version >/dev/null 2>&1 && PODMAN_AVAILABLE=true || PODMAN_AVAILABLE=false
```

**Execution Steps for Docker:**
```bash
if [ "$DOCKER_AVAILABLE" = "true" ]; then
  cd /tmp/cidx-test-docker
  rm -rf .cidx
  
  # Force Docker usage
  cidx init --embedding-provider ollama --force-docker
  cidx start
  docker ps | grep cidx
  cidx uninstall --force-docker
  
  # Verify
  docker ps -a | grep cidx
  # Expected: No containers
fi
```

**Execution Steps for Podman:**
```bash
if [ "$PODMAN_AVAILABLE" = "true" ]; then
  cd /tmp/cidx-test-podman
  rm -rf .cidx
  
  # Use Podman (default if available)
  cidx init --embedding-provider ollama
  cidx start
  podman ps | grep cidx
  cidx uninstall
  
  # Verify
  podman ps -a | grep cidx
  # Expected: No containers
fi
```

**Success Criteria:**
- ✅ Cleanup works with Docker engine
- ✅ Cleanup works with Podman engine
- ✅ Engine detection is automatic and correct
- ✅ Force flags work as expected

**Cleanup:**
```bash
rm -rf /tmp/cidx-test-docker /tmp/cidx-test-podman
```

### Test Case 7: Error Recovery and Reporting

**Objective:** Verify error handling and reporting when cleanup encounters issues.

**Test Setup:**
```bash
cd /tmp/cidx-test-errors
rm -rf .cidx
```

**Execution Steps:**
1. Initialize and start:
   ```bash
   cidx init --embedding-provider ollama
   cidx start
   ```
   
2. Create a problematic situation:
   ```bash
   # Lock a container to simulate removal failure
   CONTAINER=$(docker ps --format "{{.Names}}" | grep cidx | head -1)
   
   # Try uninstall with verbose to see error handling
   cidx uninstall --force-docker --verbose
   ```

**Verification Steps:**
1. Check error reporting:
   - Verbose output should show which containers failed
   - Error messages should be clear and actionable
   - System should attempt to continue despite individual failures
   
2. Manual verification of error guidance:
   ```bash
   # The system should provide guidance on manual cleanup if needed
   docker ps -a | grep cidx
   ```

**Success Criteria:**
- ✅ Clear error messages for failed operations
- ✅ Verbose mode provides detailed diagnostic info
- ✅ Partial cleanup continues despite individual failures
- ✅ Actionable guidance provided for manual intervention

**Cleanup:**
```bash
cd /
docker ps -a --format "{{.Names}}" | grep cidx | xargs -r docker rm -f
rm -rf /tmp/cidx-test-errors
```

### Test Case 8: Orphaned Container Cleanup

**Objective:** Verify that orphaned containers (created outside compose context) are properly removed.

**Test Setup:**
```bash
cd /tmp/cidx-test-orphans
rm -rf .cidx
```

**Execution Steps:**
1. Initialize and start normally:
   ```bash
   cidx init --embedding-provider ollama
   cidx start
   ```
   
2. Create orphaned container manually:
   ```bash
   # Get the project hash for consistent naming
   PROJECT_HASH=$(docker ps --format "{{.Names}}" | grep cidx | head -1 | cut -d'-' -f2)
   
   # Create an orphaned container with cidx naming pattern
   docker create --name "cidx-${PROJECT_HASH}-orphan" busybox sleep 1000
   ```
   
3. Verify orphan exists:
   ```bash
   docker ps -a | grep cidx
   # Should show regular containers plus the orphan
   ```
   
4. Execute uninstall:
   ```bash
   cidx uninstall --force-docker --verbose
   ```

**Verification Steps:**
1. Verify all containers removed including orphan:
   ```bash
   docker ps -a | grep cidx
   # Expected: No containers, including the manually created orphan
   ```

**Success Criteria:**
- ✅ Compose-managed containers removed
- ✅ Orphaned containers with cidx naming removed
- ✅ --remove-orphans flag effective
- ✅ Complete cleanup achieved

**Cleanup:**
```bash
cd /
rm -rf /tmp/cidx-test-orphans
```

### Test Execution Summary Checklist

**Pre-Test Validation:**
- [ ] No existing cidx containers in system
- [ ] Docker/Podman service is running
- [ ] Test directories created in /tmp
- [ ] Sufficient permissions for Docker operations

**Test Execution Order:**
1. [ ] Test Case 1: Normal Operation - PASS/FAIL
2. [ ] Test Case 2: Startup Failure - PASS/FAIL
3. [ ] Test Case 3: Mixed States - PASS/FAIL
4. [ ] Test Case 4: Rapid Cycles - PASS/FAIL
5. [ ] Test Case 5: Dependencies - PASS/FAIL
6. [ ] Test Case 6: Engine Compatibility - PASS/FAIL (if applicable)
7. [ ] Test Case 7: Error Recovery - PASS/FAIL
8. [ ] Test Case 8: Orphaned Containers - PASS/FAIL

**Post-Test Validation:**
- [ ] All test directories cleaned up
- [ ] No cidx containers remaining
- [ ] No cidx volumes remaining
- [ ] No cidx networks remaining
- [ ] System ready for production use

### Troubleshooting Guide

**If containers remain after uninstall:**
1. Check container states:
   ```bash
   docker ps -a --format "table {{.Names}}\t{{.State}}\t{{.Status}}" | grep cidx
   ```

2. Check for permission issues:
   ```bash
   docker rm -f $(docker ps -aq -f name=cidx) 2>&1 | grep -i permission
   ```

3. Force manual cleanup (last resort):
   ```bash
   docker ps -a --format "{{.Names}}" | grep cidx | xargs -r docker rm -f
   docker volume ls --format "{{.Name}}" | grep cidx | xargs -r docker volume rm -f
   docker network ls --format "{{.Name}}" | grep cidx | xargs -r docker network rm
   ```

4. Verify Docker daemon health:
   ```bash
   docker system info
   systemctl status docker  # or podman
   ```

**Common Issues and Solutions:**
- **Permission Denied**: Run with appropriate Docker group membership or sudo
- **Container Name Exists**: Indicates incomplete cleanup - bug not fully fixed
- **Timeout Errors**: Increase timeout values in force cleanup operations
- **Network Issues**: Ensure containers are disconnected from networks before removal

### Performance Benchmarks

**Expected Timing:**
- Normal uninstall: < 30 seconds
- Force cleanup per container: < 10 seconds
- Total cleanup validation: < 5 seconds
- Complete test suite execution: ~ 15-20 minutes

**Performance Validation:**
```bash
time cidx uninstall --force-docker
# Should complete within 60 seconds even in worst case
```

### Final Validation Script

Create and run this script to validate the fix comprehensively:

```bash
#!/bin/bash
# save as: /tmp/validate_cleanup_fix.sh

set -e

echo "=== CIDX Docker Cleanup Fix Validation ==="

# Function to check for remaining containers
check_containers() {
    local count=$(docker ps -a | grep cidx | wc -l)
    if [ $count -eq 0 ]; then
        echo "✅ No cidx containers found"
        return 0
    else
        echo "❌ Found $count remaining cidx containers:"
        docker ps -a --format "table {{.Names}}\t{{.State}}" | grep cidx
        return 1
    fi
}

# Test 1: Basic cycle
echo -e "\n--- Test 1: Basic Install/Uninstall ---"
cd /tmp && rm -rf cidx-validate && mkdir cidx-validate && cd cidx-validate
cidx init --embedding-provider ollama
cidx start
sleep 5
cidx uninstall --force-docker
check_containers || exit 1

# Test 2: Failure scenario
echo -e "\n--- Test 2: Startup Failure Scenario ---"
cd /tmp && rm -rf cidx-validate2 && mkdir cidx-validate2 && cd cidx-validate2
cidx init --embedding-provider ollama
# Cause intentional failure
docker run -d --name blocker -p 6333:80 busybox sleep 30 2>/dev/null || true
cidx start || true
docker rm -f blocker 2>/dev/null || true
cidx uninstall --force-docker
check_containers || exit 1

echo -e "\n=== ✅ ALL VALIDATION TESTS PASSED ==="
echo "The Docker cleanup bug fix is working correctly!"

# Cleanup
cd /tmp
rm -rf cidx-validate cidx-validate2
```

Run validation:
```bash
chmod +x /tmp/validate_cleanup_fix.sh
/tmp/validate_cleanup_fix.sh
```

This comprehensive test plan ensures complete validation of the Docker cleanup bug fix, covering all scenarios from the original bug report through edge cases and error conditions.