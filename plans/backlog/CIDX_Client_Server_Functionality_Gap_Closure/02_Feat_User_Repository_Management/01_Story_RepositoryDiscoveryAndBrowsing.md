# Story: Repository Discovery and Browsing

[Conversation Reference: "Discover and list available repositories"]

## Story Overview

**Objective**: Implement repository discovery and browsing capabilities, enabling users to see their activated repositories and discover available golden repositories for activation.

**User Value**: Users can understand what repositories they currently have access to and what additional repositories are available for activation, providing complete visibility into the repository ecosystem.

**Acceptance Criteria Summary**: Complete repository visibility with listing of activated repositories, browsing of available golden repositories, and discovery of remote repositories.

## Acceptance Criteria

### AC1: List User's Activated Repositories
**Scenario**: User views their currently activated repositories
```gherkin
Given I am authenticated with valid credentials
When I execute "cidx repos list"
Then the system should display a table of my activated repositories
And show repository alias, current branch, sync status, and last sync time
And display "No repositories activated" if I have no repositories
And provide guidance for activating repositories

Given I have multiple activated repositories
When I execute "cidx repos list"
Then the system should display all repositories in a formatted table
And sort repositories by activation date (newest first)
And show sync status indicators (✓ synced, ⚠ needs sync, ✗ conflict)
And display total count of activated repositories
```

**Technical Requirements**:
- [ ] Implement `cidx repos list` command
- [ ] Integrate with GET `/api/repos` endpoint
- [ ] Format repository list in readable table format
- [ ] Show key repository information: alias, branch, sync status, last sync
- [ ] Handle empty repository list gracefully
- [ ] Sort repositories by activation date

### AC2: Browse Available Golden Repositories
**Scenario**: User browses available repositories for activation
```gherkin
Given I am authenticated with valid credentials
When I execute "cidx repos available"
Then the system should display available golden repositories
And show repository alias, description, default branch, and indexed branches
And indicate which repositories I already have activated
And display "No repositories available" if none exist
And provide guidance for repository activation

Given some repositories are already activated
When I execute "cidx repos available"
Then the system should mark activated repositories as "Already activated"
And still show their information for reference
And highlight repositories available for activation
```

**Technical Requirements**:
- [ ] Implement `cidx repos available` command
- [ ] Integrate with GET `/api/repos/available` endpoint
- [ ] Display golden repository information in formatted table
- [ ] Show activation status for each repository
- [ ] Indicate already activated repositories
- [ ] Provide clear activation guidance

### AC3: Repository Discovery from Remote Sources
**Scenario**: User discovers repositories from remote Git sources
```gherkin
Given I am authenticated with valid credentials
When I execute "cidx repos discover --source github.com/myorg"
Then the system should search for repositories in the specified source
And display discovered repositories with their details
And show which ones are already available as golden repositories
And provide options to suggest them for administrative addition

Given I discover repositories not yet in the system
When I execute "cidx repos discover --source <git-url>"
Then the system should validate the repository accessibility
And display repository information if accessible
And provide guidance for requesting repository addition
And show contact information for administrators
```

**Technical Requirements**:
- [ ] Implement `cidx repos discover` command with source parameter
- [ ] Integrate with GET `/api/repos/discover` endpoint
- [ ] Support various source formats (GitHub org, GitLab group, direct URLs)
- [ ] Validate discovered repository accessibility
- [ ] Show discovery results with actionable next steps
- [ ] Provide guidance for repository addition requests

### AC4: Repository Information Filtering and Search
**Scenario**: User filters and searches repository lists
```gherkin
Given I have multiple repositories to browse
When I execute "cidx repos list --filter <pattern>"
Then the system should show only repositories matching the pattern
And support filtering by alias, branch, or sync status
And maintain table formatting for filtered results

When I execute "cidx repos available --search <term>"
Then the system should show only repositories with descriptions or aliases containing the term
And highlight matching terms in the results
And show total matches found
```

**Technical Requirements**:
- [ ] Add `--filter` option to `cidx repos list` command
- [ ] Add `--search` option to `cidx repos available` command
- [ ] Support pattern matching for repository filtering
- [ ] Implement case-insensitive search functionality
- [ ] Highlight search terms in results when applicable
- [ ] Maintain consistent table formatting for filtered results

### AC5: Repository Status Summary Display
**Scenario**: User gets comprehensive repository status overview
```gherkin
Given I am authenticated with valid credentials
When I execute "cidx repos status"
Then the system should display a summary of all repository information
And show total activated repositories count
And show total available repositories count
And display sync status summary (how many need sync, have conflicts, etc.)
And show recent activity (recently activated, recently synced)
And provide quick action suggestions based on status
```

**Technical Requirements**:
- [ ] Implement `cidx repos status` command for comprehensive overview
- [ ] Aggregate data from list and available endpoints
- [ ] Calculate and display summary statistics
- [ ] Show recent activity and actionable insights
- [ ] Provide personalized recommendations based on repository state
- [ ] Format information in dashboard-style layout

## Technical Implementation Details

### Command Structure
```python
@cli.group(name="repos")
@require_mode("remote")
def repos():
    """Repository management commands."""
    pass

@repos.command()
@click.option("--filter", help="Filter repositories by pattern")
def list(filter: str):
    """List activated repositories."""

@repos.command()
@click.option("--search", help="Search available repositories")
def available(search: str):
    """Show available golden repositories."""

@repos.command()
@click.option("--source", required=True, help="Repository source to discover")
def discover(source: str):
    """Discover repositories from remote sources."""

@repos.command()
def status():
    """Show comprehensive repository status."""
```

### Repository Display Formatting
```python
class RepositoryDisplayFormatter:
    @staticmethod
    def format_repository_list(repos: List[Repository]) -> str:
        """Format activated repositories as table."""

    @staticmethod
    def format_available_repositories(repos: List[GoldenRepository]) -> str:
        """Format available repositories as table."""

    @staticmethod
    def format_discovery_results(results: List[RepositoryDiscovery]) -> str:
        """Format discovery results with actionable information."""

    @staticmethod
    def format_status_summary(summary: RepositoryStatusSummary) -> str:
        """Format comprehensive status overview."""
```

### Repository Table Format Example
```
Activated Repositories (3)
┌─────────────┬──────────────┬─────────────┬──────────────┬─────────────┐
│ Alias       │ Branch       │ Sync Status │ Last Sync    │ Actions     │
├─────────────┼──────────────┼─────────────┼──────────────┼─────────────┤
│ web-app     │ main         │ ✓ Synced    │ 2 hours ago  │             │
│ api-service │ feature/v2   │ ⚠ Needs sync│ 1 day ago    │ sync        │
│ mobile-app  │ develop      │ ✗ Conflict  │ 3 days ago   │ resolve     │
└─────────────┴──────────────┴─────────────┴──────────────┴─────────────┘
```

## Testing Requirements

### Unit Test Coverage
- [ ] Repository list formatting and display logic
- [ ] Repository filtering and search algorithms
- [ ] Status summary calculation and aggregation
- [ ] Discovery result processing and validation
- [ ] Error handling for various API response scenarios

### Integration Test Coverage
- [ ] End-to-end repository listing with server data
- [ ] Available repositories browsing with activation status
- [ ] Repository discovery workflow validation
- [ ] Status summary accuracy with real repository data
- [ ] Error handling for server connectivity issues

### User Experience Testing
- [ ] Table formatting readability with various data sizes
- [ ] Search and filter functionality effectiveness
- [ ] Status summary usefulness and actionability
- [ ] Discovery workflow clarity and guidance
- [ ] Error message clarity and recovery guidance

## Performance Requirements

### Response Time Targets
- Repository list display: <2 seconds
- Available repositories browsing: <3 seconds
- Repository discovery: <10 seconds (may require network calls)
- Status summary generation: <5 seconds
- Search and filter operations: <1 second

### Data Handling Requirements
- Support for 100+ repositories without performance degradation
- Efficient filtering and search for large repository lists
- Pagination consideration for very large repository sets
- Caching of frequently accessed repository information

## User Experience Considerations

### Information Architecture
- Clear hierarchy: user repos vs available repos vs discovered repos
- Consistent status indicators across all views
- Actionable information with clear next steps
- Progressive disclosure: summary first, details on demand

### Error Handling and Guidance
- Clear messages when no repositories are available
- Guidance for activating first repository
- Help text for discovery and search functionality
- Recovery guidance for API errors

## Definition of Done

### Functional Completion
- [ ] All repository browsing commands implemented and functional
- [ ] Repository filtering and search working effectively
- [ ] Status summary providing comprehensive overview
- [ ] Discovery functionality working with various sources
- [ ] Clear guidance provided for all user scenarios

### Quality Validation
- [ ] >95% test coverage for repository browsing logic
- [ ] Performance benchmarks met for all operations
- [ ] User experience validated through testing
- [ ] Error scenarios comprehensively handled
- [ ] Information architecture clear and intuitive

### Integration Readiness
- [ ] Repository browsing foundation ready for activation commands
- [ ] Discovery results ready for activation workflow
- [ ] Status information supports operational decision making
- [ ] Table formatting patterns established for other features

---

**Story Points**: 5
**Priority**: High (Foundation for repository operations)
**Dependencies**: Enhanced Authentication Management (Feature 1) must be completed
**Success Metric**: Users can effectively browse and discover repositories with complete visibility into available options