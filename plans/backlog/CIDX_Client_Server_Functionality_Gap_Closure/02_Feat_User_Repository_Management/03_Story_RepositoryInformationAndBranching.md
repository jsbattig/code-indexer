# Story: Repository Information and Branching

[Conversation Reference: "Repository details and branch operations"]

## Story Overview

**Objective**: Implement detailed repository information display and branch management capabilities, enabling users to get comprehensive repository details and switch branches for different development contexts.

**User Value**: Users can access detailed information about their repositories and switch branches seamlessly, supporting different development workflows and providing operational visibility into repository state.

**Acceptance Criteria Summary**: Complete repository information display with branch listing, branch switching, and repository status monitoring.

## Acceptance Criteria

### AC1: Detailed Repository Information Display
**Scenario**: User views comprehensive repository information
```gherkin
Given I have an activated repository "my-project"
When I execute "cidx repos info my-project"
Then the system should display comprehensive repository information
And show alias, Git URL, current branch, and available branches
And display last sync time and sync status
And show activation date and repository statistics
And display container status and query readiness
And show recent activity and change summary
```

**Technical Requirements**:
- [x] Implement `cidx repos info` command with repository alias parameter
- [x] Integrate with GET `/api/repos/{user_alias}` endpoint
- [x] Display comprehensive repository metadata and status
- [x] Show branch information and switching capabilities
- [x] Include container and service status information
- [x] Format information in readable, structured layout

### AC2: Branch Listing and Status Display
**Scenario**: User views branch information and status
```gherkin
Given I have an activated repository with multiple branches
When I execute "cidx repos info my-project --branches"
Then the system should list all available branches
And mark the current branch clearly
And show last commit information for each branch
And indicate which branches are available locally vs remotely
And display branch sync status with golden repository
```

**Technical Requirements**:
- [x] Add `--branches` option for detailed branch information
- [x] List local and remote branches with status indicators
- [x] Show current branch with clear marking
- [x] Display last commit information and timestamps
- [x] Indicate branch sync status and availability

### AC3: Branch Switching Operations
**Scenario**: User switches branches in activated repository
```gherkin
Given I have an activated repository "my-project" on branch "main"
When I execute "cidx repos switch-branch my-project develop"
Then the system should switch to the "develop" branch
And update the repository working directory
And display "Switched to branch 'develop' in repository 'my-project'"
And update container configuration if needed
And preserve any local uncommitted changes appropriately

Given the target branch doesn't exist locally
When I execute "cidx repos switch-branch my-project feature/new"
Then the system should check if branch exists remotely
And create local tracking branch if remote exists
And display "Created and switched to new branch 'feature/new'"
And provide guidance if branch doesn't exist anywhere
```

**Technical Requirements**:
- [x] Implement `cidx repos switch-branch` command
- [x] Integrate with PUT `/api/repos/{user_alias}/branch` endpoint
- [x] Handle local and remote branch switching
- [x] Create local tracking branches for remote branches
- [x] Preserve uncommitted changes during branch switching
- [x] Update container configuration for new branch context

### AC4: Repository Status and Health Monitoring
**Scenario**: User monitors repository health and operational status
```gherkin
Given I have activated repositories
When I execute "cidx repos info my-project --health"
Then the system should display repository health information
And show container status (running, stopped, failed)
And display index status and query readiness
And show disk usage and storage information
And indicate any issues requiring attention
And provide actionable recommendations for problems
```

**Technical Requirements**:
- [x] Add `--health` option for comprehensive health checking
- [x] Monitor container status and service availability
- [x] Check index integrity and query readiness
- [x] Display storage usage and capacity information
- [x] Identify and report repository health issues
- [x] Provide actionable recommendations for problem resolution

### AC5: Repository Activity and Change Tracking
**Scenario**: User views repository activity and recent changes
```gherkin
Given I have repositories with recent activity
When I execute "cidx repos info my-project --activity"
Then the system should show recent repository activity
And display recent commits and changes
And show sync history and timing
And indicate recent branch switches or operations
And display query activity and usage patterns
And provide insights about repository utilization
```

**Technical Requirements**:
- [x] Add `--activity` option for activity monitoring
- [x] Display recent commits and repository changes
- [x] Show sync history and operational timeline
- [x] Track branch operations and user activity
- [x] Monitor query usage and access patterns
- [x] Provide utilization insights and recommendations

## Technical Implementation Details

### Command Structure Extension
```python
@repos.command()
@click.argument("user_alias")
@click.option("--branches", is_flag=True, help="Show detailed branch information")
@click.option("--health", is_flag=True, help="Show repository health status")
@click.option("--activity", is_flag=True, help="Show recent repository activity")
def info(user_alias: str, branches: bool, health: bool, activity: bool):
    """Show detailed repository information."""

@repos.command(name="switch-branch")
@click.argument("user_alias")
@click.argument("branch_name")
@click.option("--create", is_flag=True, help="Create branch if it doesn't exist")
def switch_branch(user_alias: str, branch_name: str, create: bool):
    """Switch branch in activated repository."""
```

### Repository Information Display Format
```
Repository Information: my-project
=====================================
Basic Information:
  Alias: my-project
  Golden Repository: web-application
  Git URL: https://github.com/company/web-app.git
  Current Branch: feature/auth-improvements
  Activated: 2024-01-15 10:30:00 (3 days ago)

Branch Information:
  * feature/auth-improvements (current)
    └── Last commit: feat: add OAuth integration (2 hours ago)
  main
    └── Last commit: fix: resolve login timeout issue (1 day ago)
  develop
    └── Last commit: chore: update dependencies (3 days ago)

Status:
  Sync Status: ✓ Up to date with golden repository
  Last Sync: 2024-01-15 14:22:00 (30 minutes ago)
  Container Status: ✓ Running and ready for queries
  Index Status: ✓ Fully indexed (1,234 files)
  Query Readiness: ✓ Ready

Storage Information:
  Disk Usage: 156 MB (shared: 142 MB, unique: 14 MB)
  Index Size: 23 MB
  Available Space: 45.2 GB
```

## Integration with Repository Architecture

### Container Status Integration
**Container Monitoring**: Check status of repository-specific containers
**Port Information**: Display allocated ports and service availability
**Health Validation**: Verify container health and connectivity
**Auto-Recovery**: Suggest container restart if services are down

### CoW Storage Information
**Shared Storage**: Display shared vs unique storage usage
**Index Sharing**: Show index sharing status with golden repository
**Storage Efficiency**: Calculate and display storage efficiency metrics
**Cleanup Recommendations**: Suggest cleanup when storage usage is high

## Testing Requirements

### Unit Test Coverage
- [x] Repository information formatting and display logic
- [x] Branch listing and status calculation
- [x] Branch switching command validation and execution
- [x] Health monitoring and status aggregation
- [x] Activity tracking and display formatting

### Integration Test Coverage
- [x] End-to-end repository information retrieval
- [x] Branch switching with server-side Git operations
- [x] Health monitoring with real container status
- [x] Activity tracking with actual repository operations
- [x] Information display accuracy with various repository states

### User Experience Testing
- [x] Information layout readability and comprehensiveness
- [x] Branch switching workflow intuitiveness
- [x] Health status clarity and actionability
- [x] Activity information usefulness for operational decisions
- [x] Error handling and guidance quality

## Performance Requirements

### Response Time Targets
- Repository info display: <2 seconds
- Branch listing: <3 seconds
- Branch switching: <10 seconds for complex operations
- Health checking: <5 seconds for comprehensive checks
- Activity display: <3 seconds for recent activity

### Information Accuracy Requirements
- Real-time container status accuracy
- Current branch information always accurate
- Sync status updated within 1 minute of changes
- Storage information updated within 5 minutes
- Activity information captured within 30 seconds of operations

## Definition of Done

### Functional Completion
- [x] Repository information command with comprehensive display
- [x] Branch listing and switching operations working
- [x] Health monitoring providing actionable insights
- [x] Activity tracking showing relevant operational information
- [x] All information display options functioning correctly

### Quality Validation
- [x] >95% test coverage for information and branching logic
- [x] Performance benchmarks met for all information operations
- [x] User experience validated for information clarity
- [x] Integration with repository architecture verified
- [x] Error scenarios comprehensively handled

### Integration Readiness
- [x] Repository information supporting operational decisions
- [x] Branch switching integrated with container lifecycle
- [x] Health monitoring ready for system health features
- [x] Activity information supporting usage analytics

---

**Story Points**: 5
**Priority**: Medium (Important for repository operations)
**Dependencies**: Repository Activation Lifecycle (Story 2) must be completed
**Success Metric**: Users have complete visibility into repository state with effective branch management capabilities