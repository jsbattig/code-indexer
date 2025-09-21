# Story: Repository Activation Lifecycle

[Conversation Reference: "Activate and deactivate repositories"]

## Story Overview

**Objective**: Implement complete repository activation and deactivation workflow, enabling users to create personal instances of golden repositories and manage their lifecycle effectively.

**User Value**: Users can activate golden repositories for personal use with CoW cloning benefits and deactivate them when no longer needed, providing efficient repository lifecycle management with storage optimization.

**Acceptance Criteria Summary**: Complete activation/deactivation workflow with CoW cloning, lifecycle management, and proper cleanup procedures.

## Acceptance Criteria

### AC1: Repository Activation from Golden Repository
**Scenario**: User activates a golden repository for personal use
```gherkin
Given I am authenticated with valid credentials
And there are golden repositories available for activation
When I execute "cidx repos activate <golden-alias> --as <my-alias>"
Then the system should create a CoW clone of the golden repository
And configure the activated repository with proper remote origins
And display activation progress with status updates
And show "Repository '<my-alias>' activated successfully"
And make the repository available for query operations
And display next steps for using the activated repository

Given I activate a repository without specifying an alias
When I execute "cidx repos activate <golden-alias>"
Then the system should use the golden repository alias as the user alias
And proceed with activation using the default naming
```

**Technical Requirements**:
- [x] Implement `cidx repos activate` command with golden-alias and optional user-alias
- [x] Integrate with POST `/api/repos/activate` endpoint
- [x] Display activation progress with status updates
- [x] Handle CoW cloning through server infrastructure
- [x] Validate golden repository availability before activation
- [x] Support custom user alias or default to golden alias
- [x] Provide clear success messaging and next steps

### AC2: Repository Activation Conflict Handling
**Scenario**: User handles activation conflicts and constraints
```gherkin
Given I already have a repository activated with alias "web-app"
When I execute "cidx repos activate another-golden --as web-app"
Then the system should display "Alias 'web-app' already in use"
And suggest alternative aliases or deactivation of existing repository
And not proceed with activation
And preserve existing repository state

Given a golden repository is not available for activation
When I execute "cidx repos activate unavailable-repo"
Then the system should display "Repository 'unavailable-repo' not found or not available"
And list available repositories for activation
And provide guidance for requesting repository addition
```

**Technical Requirements**:
- [x] Validate user alias uniqueness before activation
- [x] Check golden repository availability and accessibility
- [x] Provide helpful error messages with alternatives
- [x] Suggest available repositories when activation fails
- [x] Handle server-side activation constraints gracefully
- [x] Preserve existing repository state during failed activations

### AC3: Repository Deactivation with Cleanup
**Scenario**: User deactivates repository with proper cleanup
```gherkin
Given I have an activated repository "my-project"
When I execute "cidx repos deactivate my-project"
Then the system should prompt "Deactivate repository 'my-project'? This will remove all local data. (y/N)"
And I confirm with "y"
And the system should stop any running containers for the repository
And remove the activated repository directory structure
And clean up associated configuration and metadata
And display "Repository 'my-project' deactivated successfully"
And remove the repository from my activated repositories list

Given I have uncommitted changes in the repository
When I execute "cidx repos deactivate my-project"
Then the system should warn "Repository has uncommitted changes that will be lost"
And prompt for confirmation with enhanced warning
And require explicit confirmation to proceed
```

**Technical Requirements**:
- [x] Implement `cidx repos deactivate` command with repository alias
- [x] Integrate with DELETE `/api/repos/{user_alias}` endpoint
- [x] Provide confirmation prompts for destructive operations
- [x] Check for uncommitted changes and warn appropriately
- [x] Stop containers and clean up resources properly
- [x] Remove repository from activated list after successful deactivation
- [x] Handle partial deactivation failures with proper error reporting

### AC4: Forced Deactivation and Recovery
**Scenario**: User handles problematic repositories requiring forced deactivation
```gherkin
Given I have a corrupted or problematic repository "broken-repo"
When I execute "cidx repos deactivate broken-repo --force"
Then the system should skip normal cleanup validations
And forcefully remove the repository and associated resources
And display warnings about potential resource leaks
And show "Repository 'broken-repo' forcefully deactivated"
And provide guidance for cleaning up any remaining resources

Given deactivation fails due to resource conflicts
When I execute "cidx repos deactivate stuck-repo --force"
Then the system should attempt container force-stop operations
And proceed with directory removal regardless of container state
And log cleanup issues for administrative review
And complete deactivation with warnings about partial cleanup
```

**Technical Requirements**:
- [x] Add `--force` option for problematic repository cleanup
- [x] Implement forced container stopping and resource cleanup
- [x] Skip normal validation steps during forced deactivation
- [x] Provide warnings about potential resource leaks
- [x] Log cleanup issues for administrative review
- [x] Complete deactivation even with partial cleanup failures

### AC5: Activation Status and Lifecycle Monitoring
**Scenario**: User monitors activation lifecycle and status
```gherkin
Given I am activating a large repository
When the activation process is running
Then the system should display real-time progress updates
And show current step (cloning, configuring, indexing)
And display estimated time remaining when available
And allow cancellation with Ctrl+C if needed

Given activation takes longer than expected
When I execute "cidx repos status" during activation
Then the system should show "Activating: <repo-alias> (in progress)"
And display current activation step and progress
And provide option to check detailed activation logs

Given activation fails partway through
When the process encounters an error
Then the system should display specific error information
And automatically clean up partial activation artifacts
And restore system to pre-activation state
And provide troubleshooting guidance
```

**Technical Requirements**:
- [x] Implement real-time progress reporting during activation
- [x] Show activation status in repository status commands
- [x] Handle activation cancellation gracefully
- [x] Automatic cleanup of failed activation attempts
- [x] Detailed error reporting with troubleshooting guidance
- [x] Activation state persistence for monitoring

## Technical Implementation Details

### Command Structure Extension
```python
@repos.command()
@click.argument("golden_alias")
@click.option("--as", "user_alias", help="Alias for activated repository")
@click.option("--branch", help="Initial branch to activate")
def activate(golden_alias: str, user_alias: str, branch: str):
    """Activate a golden repository for personal use."""

@repos.command()
@click.argument("user_alias")
@click.option("--force", is_flag=True, help="Force deactivation of problematic repositories")
@click.confirmation_option(prompt="Deactivate repository? This will remove all local data.")
def deactivate(user_alias: str, force: bool):
    """Deactivate a personal repository."""
```

### Activation Progress Display
```python
class ActivationProgressDisplay:
    def show_activation_progress(self, golden_alias: str, user_alias: str):
        """Display real-time activation progress."""

    def show_activation_steps(self, current_step: str, progress: float):
        """Show current activation step with progress."""

    def show_activation_complete(self, user_alias: str, next_steps: List[str]):
        """Display completion message with next steps."""
```

### Repository Lifecycle State Management
```python
@dataclass
class ActivationRequest:
    golden_alias: str
    user_alias: str
    target_branch: Optional[str]
    activation_options: Dict[str, Any]

@dataclass
class ActivationProgress:
    status: str  # 'initializing', 'cloning', 'configuring', 'indexing', 'completed'
    progress_percent: float
    current_step: str
    estimated_remaining: Optional[int]
    error_message: Optional[str]
```

## CoW Cloning Architecture Integration

### Server-Side CoW Implementation
**Golden Repository Location**: `~/.cidx-server/data/golden-repos/<alias>/`
**Activated Repository Location**: `~/.cidx-server/data/activated-repos/<username>/<user_alias>/`
**CoW Strategy**: `git clone --local` with shared object storage
**Index Sharing**: `.code-indexer/` directory included in CoW clone for immediate query capability

### Container Management Integration
**Container Lifecycle**: Activated repositories get their own container set
**Port Allocation**: Dynamic port calculation based on activated repository path
**Resource Isolation**: Each activated repository has independent container resources
**Auto-Startup**: Containers start automatically when queries are made to the repository

## Testing Requirements

### Unit Test Coverage
- [x] Repository activation command logic and validation
- [x] Deactivation workflow with confirmation handling
- [x] Error handling for various activation failure scenarios
- [x] Progress reporting and status monitoring logic
- [x] Forced deactivation and cleanup procedures

### Integration Test Coverage
- [x] End-to-end activation workflow with server CoW cloning
- [x] Deactivation workflow with proper resource cleanup
- [x] Activation progress monitoring with real server operations
- [x] Error recovery and cleanup validation
- [x] Container lifecycle integration during activation/deactivation

### Repository State Testing
- [x] CoW cloning verification and shared resource validation
- [x] Repository state consistency after activation/deactivation
- [x] Container and port allocation validation
- [x] Resource cleanup completeness verification
- [x] Activation cancellation and recovery testing

## Performance Requirements

### Activation Performance Targets
- Small repository activation: <30 seconds
- Large repository activation: <5 minutes with progress updates
- Deactivation: <10 seconds for cleanup completion
- Progress updates: Real-time with <1 second latency
- Error recovery: <5 seconds for cleanup operations

### Resource Management Requirements
- CoW cloning efficiency: Minimal additional storage for shared indexes
- Container startup: <30 seconds for activated repository containers
- Memory usage: <50MB additional during activation operations
- Cleanup completeness: 100% resource cleanup during deactivation

## Error Handling and Recovery

### Activation Error Scenarios
```
Repository activation failed: Golden repository 'repo-name' not found
Activation failed: Insufficient disk space for repository cloning
CoW cloning failed: Unable to create repository instance
Container setup failed: Port allocation conflict detected
Network error: Unable to reach server during activation
```

### Recovery Procedures
- Automatic cleanup of partial activation on failure
- Clear guidance for resolving common activation issues
- Administrative contact information for complex problems
- Retry mechanisms for transient network or resource issues

## Definition of Done

### Functional Completion
- [x] Repository activation command working with CoW cloning integration
- [x] Repository deactivation with proper cleanup and confirmation
- [x] Progress monitoring and status display during operations
- [x] Error handling and recovery for all failure scenarios
- [x] Forced deactivation for problematic repository cleanup

### Quality Validation
- [x] >95% test coverage for activation/deactivation logic
- [x] Performance benchmarks met for all repository operations
- [x] Resource cleanup validation for all deactivation scenarios
- [x] User experience validated through end-to-end testing
- [x] Error recovery procedures thoroughly tested

### Integration Readiness
- [x] Repository activation ready for branching and info operations
- [x] CoW cloning working with container lifecycle management
- [x] Resource cleanup supporting system health monitoring
- [x] Activation status supporting operational dashboards

---

**Story Points**: 8
**Priority**: Critical (Core repository management functionality)
**Dependencies**: Repository Discovery and Browsing (Story 1) must be completed
**Success Metric**: Users can reliably activate and deactivate repositories with proper resource management and CoW storage efficiency