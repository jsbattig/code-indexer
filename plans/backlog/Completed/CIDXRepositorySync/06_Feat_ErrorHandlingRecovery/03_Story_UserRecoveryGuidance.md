# Story 6.3: User Recovery Guidance

## Story Description

As a CIDX user experiencing sync errors, I need clear, actionable guidance on how to resolve issues, with step-by-step instructions, helpful documentation links, and support options that help me recover quickly.

## Technical Specification

### User Guidance System

```pseudocode
class UserGuidanceGenerator:
    def generateGuidance(error: ClassifiedError) -> UserGuidance:
        guidance = UserGuidance {
            errorSummary: humanizeError(error),
            rootCause: explainCause(error),
            immediateActions: getImmediateSteps(error),
            troubleshooting: getTroubleshootingSteps(error),
            documentation: getRelevantDocs(error),
            supportOptions: getSupportChannels(error),
            preventionTips: getPreventionAdvice(error)
        }

        # Personalize based on context
        if error.context.hasUserHistory:
            guidance.previousOccurrences = getErrorHistory(error.code)
            guidance.previousSolutions = getSuccessfulFixes(error.code)

        return guidance

class ActionStep:
    order: int
    description: string
    command: string          # Optional CLI command
    expectedResult: string
    alternativeIf: string    # Alternative if step fails
    screenshot: string        # Optional visual aid
```

### Recovery Workflow

```pseudocode
class RecoveryWorkflow:
    def guideRecovery(error: ClassifiedError):
        guidance = generateGuidance(error)

        # Present initial summary
        displayErrorSummary(guidance.errorSummary)

        # Offer automated recovery if available
        if hasAutomatedRecovery(error):
            if promptUser("Try automatic recovery?"):
                result = attemptAutomatedRecovery()
                if result.success:
                    return SUCCESS

        # Guide through manual steps
        for step in guidance.immediateActions:
            displayStep(step)
            if promptUser("Did this resolve the issue?"):
                recordSolution(error, step)
                return SUCCESS

        # Escalate to support
        offerSupportOptions(guidance.supportOptions)
```

## Acceptance Criteria

### Error Messages
```gherkin
Given an error occurs
When displaying to user
Then the message should:
  - Use plain language (no jargon)
  - Explain what went wrong
  - Indicate impact on operation
  - Provide error code for reference
  - Show timestamp
And be under 3 sentences
```

### Solution Steps
```gherkin
Given recovery guidance needed
When providing solution steps
Then each step should:
  - Be numbered and ordered
  - Include specific commands
  - Explain expected outcomes
  - Provide alternatives if fails
  - Include verification steps
And be actionable
```

### Documentation Links
```gherkin
Given an error with documentation
When providing help links
Then the system should:
  - Link to specific error page
  - Include relevant guides
  - Provide video tutorials if available
  - Link to FAQ section
  - Ensure links are valid
And open in browser
```

### Support Options
```gherkin
Given unresolved error
When offering support
Then options should include:
  - Community forum link
  - Support ticket creation
  - Error log location
  - Diagnostic data collection
  - Contact information
And be easily accessible
```

### Prevention Advice
```gherkin
Given error resolution
When providing prevention tips
Then the system should suggest:
  - Configuration changes
  - Best practices
  - Common pitfalls to avoid
  - Monitoring recommendations
  - Update notifications
And help avoid recurrence
```

## Completion Checklist

- [ ] Error messages
  - [ ] Message templates
  - [ ] Plain language rules
  - [ ] Localization support
  - [ ] Severity indicators
- [ ] Solution steps
  - [ ] Step generator
  - [ ] Command formatting
  - [ ] Verification logic
  - [ ] Alternative paths
- [ ] Documentation links
  - [ ] URL mapping
  - [ ] Link validation
  - [ ] Browser opening
  - [ ] Offline fallback
- [ ] Support options
  - [ ] Channel configuration
  - [ ] Ticket creation
  - [ ] Log collection
  - [ ] Contact details

## Test Scenarios

### Happy Path
1. Error occurs → Clear message → User fixes → Success
2. Complex error → Step-by-step guide → Resolution achieved
3. Unknown error → Support offered → Ticket created
4. Repeated error → Previous solution shown → Quick fix

### Error Cases
1. Guidance fails → Escalate to support → Alternative help
2. Links broken → Fallback to offline → Local docs shown
3. Steps unclear → User feedback → Guidance improved
4. No internet → Offline guidance → Cache used

### Edge Cases
1. Multiple errors → Prioritized guidance → Most critical first
2. Language barrier → Localized help → Translated guidance
3. Terminal-only → Text formatting → No rich display
4. First-time user → Extra context → Detailed explanation

## Performance Requirements

- Guidance generation: <100ms
- Documentation lookup: <200ms
- Link validation: Async/cached
- History search: <50ms
- Display rendering: <50ms

## Error Message Examples

### Network Timeout
```
❌ Connection to server timed out (NET-001)

Unable to reach the sync server after 30 seconds.
This is usually temporary and caused by network issues.

🔧 Quick fixes to try:
  1. Check your internet connection
     $ ping github.com
     ✓ Should see responses

  2. Verify the server is accessible
     $ cidx status --check-server
     ✓ Should show "Server: Online"

  3. Try again with extended timeout
     $ cidx sync --timeout 120

💡 If the issue persists:
  • Your firewall may be blocking connections
  • The server may be experiencing high load
  • View detailed logs: ~/.cidx/logs/sync.log

📚 Documentation: https://cidx.io/help/NET-001
💬 Get help: https://forum.cidx.io/network-issues
```

### Git Merge Conflict
```
⚠️ Merge conflicts prevent automatic sync (GIT-001)

3 files have conflicts that need manual resolution:
  • src/main.py (12 conflicts)
  • src/config.py (3 conflicts)
  • tests/test_main.py (1 conflict)

📝 To resolve conflicts:

  1. View conflict details
     $ git status
     ✓ Shows files with conflicts

  2. Open each file and look for conflict markers
     <<<<<<< HEAD
     your changes
     =======
     remote changes
     >>>>>>> origin/main

  3. Edit files to resolve conflicts
     - Keep your changes, remote changes, or combine
     - Remove all conflict markers

  4. Mark conflicts as resolved
     $ git add src/main.py src/config.py tests/test_main.py
     $ git commit -m "Resolved merge conflicts"

  5. Resume sync
     $ cidx sync

🎥 Video guide: https://cidx.io/videos/resolve-conflicts
📚 Detailed guide: https://cidx.io/help/GIT-001
💬 Need help? Post in forum with your conflict details
```

### Authentication Failure
```
🔒 Authentication failed - invalid credentials (AUTH-002)

Your access token has been rejected by the server.
You need to re-authenticate to continue.

🔑 To fix authentication:

  1. Clear existing credentials
     $ cidx logout
     ✓ Should show "Logged out successfully"

  2. Login with your account
     $ cidx login
     ✓ Will open browser for authentication

  3. Verify authentication
     $ cidx whoami
     ✓ Should show your username

⚠️ Common issues:
  • Password recently changed? You must re-login
  • Using SSO? Ensure your session is active
  • Token expired? Tokens expire after 30 days

🔐 Security tip: Never share your access token
📚 Auth guide: https://cidx.io/help/authentication
💬 Account issues: support@cidx.io
```

## Support Escalation Path

```
Level 1: Self-Service
  ↓ (If unresolved)
Level 2: Community Forum
  ↓ (If urgent/complex)
Level 3: Support Ticket
  ↓ (If critical)
Level 4: Direct Support
```

## Diagnostic Data Collection

```pseudocode
class DiagnosticCollector:
    def collectForError(error: ClassifiedError):
        diagnostics = {
            errorDetails: error.toDict(),
            systemInfo: getSystemInfo(),
            configSnapshot: getConfig(sanitized=true),
            recentLogs: getRecentLogs(lines=100),
            gitStatus: getGitStatus(),
            diskSpace: getDiskUsage(),
            networkTest: testConnectivity(),
            timestamp: now()
        }

        # Save to file
        filename = f"~/.cidx/diagnostics/{error.code}_{timestamp}.json"
        saveDiagnostics(diagnostics, filename)

        return filename
```

## Definition of Done

- [ ] Clear error messages for all error types
- [ ] Step-by-step recovery guides created
- [ ] Documentation links mapped and validated
- [ ] Support options configured
- [ ] Prevention tips documented
- [ ] Diagnostic collection implemented
- [ ] Message templates localization-ready
- [ ] Unit tests >90% coverage
- [ ] User testing validates clarity
- [ ] Performance requirements met