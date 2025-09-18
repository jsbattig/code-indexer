# Story 4.1: Sync Command Structure

## Story Description

As a CIDX CLI user, I need a simple `cidx sync` command that synchronizes my linked repository with the remote and updates the semantic index, providing a single command for keeping my codebase current.

## Technical Specification

### Command Interface

```bash
cidx sync [OPTIONS]

Options:
  --full              Force full re-indexing instead of incremental
  --branch BRANCH     Sync specific branch (default: current)
  --timeout SECONDS   Maximum time to wait (default: 300)
  --no-index          Skip semantic indexing after git sync
  --strategy STRATEGY Merge strategy: merge|rebase|theirs|ours
  --quiet             Suppress progress output
  --json              Output results as JSON
```

### Command Implementation

```pseudocode
class SyncCommand:
    def execute(args: Arguments):
        # Step 1: Validate environment
        config = loadProjectConfig()
        validateLinkedRepository(config)

        # Step 2: Authenticate
        token = getOrRefreshToken()
        client = APIClient(token)

        # Step 3: Start sync job
        options = buildSyncOptions(args)
        response = client.post("/api/sync", options)
        jobId = response.jobId

        # Step 4: Poll for completion
        result = pollUntilComplete(jobId, args.timeout)

        # Step 5: Display results
        if args.json:
            outputJSON(result)
        else:
            displaySyncSummary(result)

class SyncOptions:
    fullReindex: bool = false
    branch: string = "current"
    skipIndexing: bool = false
    mergeStrategy: string = "merge"
```

## Acceptance Criteria

### Command Parsing
```gherkin
Given I run "cidx sync" with various options
When the command is parsed
Then it should:
  - Accept all documented options
  - Validate option values
  - Set appropriate defaults
  - Handle invalid options gracefully
And provide clear usage help
```

### Authentication Flow
```gherkin
Given I need to sync a repository
When authentication is required
Then the system should:
  - Check for valid JWT token
  - Refresh if token near expiry
  - Prompt for login if needed
  - Store refreshed token securely
And proceed only when authenticated
```

### Job Initiation
```gherkin
Given valid authentication and options
When initiating a sync job
Then the CLI should:
  - Send POST request to /api/sync
  - Include project ID and options
  - Receive job ID in response
  - Handle API errors gracefully
And begin polling immediately
```

### Result Display
```gherkin
Given a sync operation has completed
When displaying results
Then the CLI should show:
  - Success/failure status
  - Files changed count
  - Indexing statistics
  - Total execution time
  - Any warnings or errors
And format based on output preference
```

### Error Handling
```gherkin
Given various error conditions
When errors occur
Then the CLI should:
  - Show clear error messages
  - Suggest corrective actions
  - Exit with appropriate code
  - Clean up any resources
And maintain consistent state
```

## Completion Checklist

- [ ] Command parsing
  - [ ] Argument parser setup
  - [ ] Option validation
  - [ ] Default values
  - [ ] Help text
- [ ] Authentication flow
  - [ ] Token validation
  - [ ] Token refresh logic
  - [ ] Secure storage
  - [ ] Login prompt
- [ ] Job initiation
  - [ ] API client setup
  - [ ] Request formatting
  - [ ] Response parsing
  - [ ] Error handling
- [ ] Result display
  - [ ] Text formatting
  - [ ] JSON output
  - [ ] Progress indicators
  - [ ] Summary statistics

## Test Scenarios

### Happy Path
1. Simple sync → Completes successfully → Shows summary
2. With --full → Full re-index → Complete statistics
3. With --branch → Specific branch → Synced correctly
4. With --json → JSON output → Parseable format

### Error Cases
1. No linked repo → Clear error: "No repository linked"
2. Invalid branch → Error: "Branch 'xyz' not found"
3. Auth failure → Prompt for login → Retry
4. Network error → Retry with message → Eventually fail

### Edge Cases
1. Token expires during sync → Auto-refresh → Continue
2. Ctrl+C during operation → Graceful shutdown → Cleanup
3. Server timeout → Client-side timeout → Error message
4. Conflicting options → Validation error → Usage help

## Performance Requirements

- Command startup: <100ms
- Authentication: <500ms
- Job initiation: <1 second
- Polling overhead: <50ms per check
- Result display: <100ms

## Output Formats

### Standard Output
```
🔄 Syncing repository...
   Repository: github.com/user/project
   Branch: main → origin/main
   Strategy: merge

📊 Git Sync Progress
   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░ 90% | Merging changes...

✅ Sync completed successfully!

📈 Summary:
   • Files changed: 42
   • Files added: 12
   • Files deleted: 3
   • Files indexed: 51
   • Embeddings created: 1,247
   • Time elapsed: 45.2s

⚠️  Warnings:
   • 3 files skipped (binary)
   • 1 file too large for indexing
```

### JSON Output
```json
{
  "status": "success",
  "jobId": "abc-123-def",
  "repository": "github.com/user/project",
  "branch": "main",
  "gitSync": {
    "filesChanged": 42,
    "filesAdded": 12,
    "filesDeleted": 3,
    "conflicts": 0
  },
  "indexing": {
    "filesIndexed": 51,
    "embeddingsCreated": 1247,
    "embeddingsUpdated": 892,
    "embeddingsDeleted": 45
  },
  "duration": 45.2,
  "warnings": [
    "3 files skipped (binary)",
    "1 file too large for indexing"
  ]
}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Authentication failure |
| 3 | Network error |
| 4 | Timeout |
| 5 | Merge conflict |
| 130 | Interrupted (Ctrl+C) |

## Definition of Done

- [ ] Command structure implemented
- [ ] All options parsed correctly
- [ ] Authentication flow complete
- [ ] Job initiation working
- [ ] Result display formatted
- [ ] Error messages helpful
- [ ] Exit codes appropriate
- [ ] Unit tests >90% coverage
- [ ] Integration tests with server
- [ ] Performance targets met