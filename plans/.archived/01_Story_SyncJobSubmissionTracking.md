# Story 12.1: Sync Job Submission and Tracking

## 🎯 **Story Intent**

Validate sync job submission and tracking functionality to ensure users can submit repository sync operations and monitor their execution lifecycle.

[Manual Testing Reference: "Sync job lifecycle validation"]

## 📋 **Story Description**

**As a** Developer using remote CIDX
**I want to** submit sync jobs and track their execution status
**So that** I can monitor long-running sync operations and verify successful completion

[Conversation Reference: "Background job submission and status tracking"]

## 🔧 **Test Procedures**

### Test 12.1.1: Basic Sync Job Submission
**Command to Execute:**
```bash
cd /path/to/remote/project
python -m code_indexer.cli sync --timeout 600
```

**Expected Results:**
- Sync command submits job to server successfully
- Returns job ID for tracking
- Job appears in server job management system
- Command displays initial job status information
- Background job execution begins immediately

**Pass/Fail Criteria:**
- ✅ PASS: Job submitted successfully with tracking ID returned
- ❌ FAIL: Job submission fails or no tracking information provided

### Test 12.1.2: Job Status Query via API
**Command to Execute:**
```bash
# Get job ID from sync command output, then:
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/jobs/{job_id}"
```

**Expected Results:**
- API returns detailed job status information
- Shows current job phase (git pull, indexing, etc.)
- Displays progress percentage if available
- Indicates estimated completion time
- Provides job execution history and timing

**Pass/Fail Criteria:**
- ✅ PASS: Job status API returns accurate and detailed information
- ❌ FAIL: API fails or returns incomplete/incorrect job data

### Test 12.1.3: Job Progress Monitoring During Execution
**Command to Execute:**
```bash
# Monitor job status every 5 seconds during execution
while true; do
  curl -s -H "Authorization: Bearer $TOKEN" \
       "http://127.0.0.1:8095/api/jobs/{job_id}" | jq '.status, .progress_percentage'
  sleep 5
done
```

**Expected Results:**
- Job status progresses through expected phases
- Progress percentage increases over time
- Status changes reflect actual sync operations
- Final status shows completion or failure
- Timing information tracks actual execution

**Pass/Fail Criteria:**
- ✅ PASS: Job progress accurately reflects sync operations
- ❌ FAIL: Inaccurate progress or status information

### Test 12.1.4: Completed Job Information Validation
**Command to Execute:**
```bash
# After job completion:
curl -H "Authorization: Bearer $TOKEN" \
     "http://127.0.0.1:8095/api/jobs/{job_id}" | jq '.'
```

**Expected Results:**
- Job shows final completion status (success/failure)
- Execution time and resource usage recorded
- Summary of operations performed (files processed, changes applied)
- Error information if job failed
- Job retained for history and debugging

**Pass/Fail Criteria:**
- ✅ PASS: Complete job information available after execution
- ❌ FAIL: Missing or incorrect completion information

## 📊 **Success Metrics**

- **Job Submission Success**: 100% successful job creation and tracking
- **Status Accuracy**: Real-time status reflects actual sync operations
- **Progress Tracking**: Accurate progress reporting throughout execution
- **Completion Recording**: Complete job history and results available

## 🎯 **Acceptance Criteria**

- [ ] Sync commands successfully submit jobs with tracking IDs
- [ ] Job status API provides accurate real-time information
- [ ] Job progress accurately reflects sync operation phases
- [ ] Completed jobs retain comprehensive execution information
- [ ] Job tracking works for both successful and failed operations
- [ ] Multiple concurrent jobs can be tracked independently

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Remote CIDX project with valid authentication
- Repository requiring synchronization (with changes to sync)
- Valid JWT token for API access
- Network connectivity to CIDX server

**Test Environment Setup:**
1. Ensure repository has content requiring synchronization
2. Verify authentication and repository linking working
3. Prepare API access with valid authentication tokens
4. Plan for monitoring job execution timing

**Job Submission Scenarios:**
- Sync with substantial repository changes
- Sync with minimal or no changes (fast completion)
- Sync with network connectivity issues
- Concurrent sync job submissions

**Post-Test Validation:**
1. Verify sync operations actually performed correctly
2. Confirm repository state matches job completion status
3. Check job information accuracy against actual operations
4. Validate job history retention and accessibility

**Common Issues:**
- Authentication token expiration during long jobs
- Network connectivity affecting job execution
- Resource limitations causing job failures
- Concurrent job limits affecting submission

**Monitoring Best Practices:**
- Use reasonable polling intervals (5-10 seconds)
- Monitor resource usage during job execution
- Track job timing for performance analysis
- Verify job cleanup and retention policies

[Manual Testing Reference: "Sync job submission and tracking validation procedures"]