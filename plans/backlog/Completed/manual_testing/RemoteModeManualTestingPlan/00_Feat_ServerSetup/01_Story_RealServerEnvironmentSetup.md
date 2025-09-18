# Story 0.1: Real Server Environment Setup

## 🎯 **Story Intent**

Establish a working CIDX server environment with real repository indexing for comprehensive remote mode testing.

[Conversation Reference: "CIDX Server (localhost:8095) - REAL SERVER REQUIRED"]

## 📋 **Story Description**

**As a** Manual Tester
**I want to** set up a real CIDX server with indexed repository
**So that** I can perform authentic remote mode testing

## 🔧 **Test Procedures**

### Test 0.1.1: Start CIDX Server
**Command to Execute:**
```bash
# Navigate to code-indexer project
cd /home/jsbattig/Dev/code-indexer

# Start server on port 8095 (keep running)
python -m code_indexer.server.main --port 8095
```

**Expected Results:**
- Server starts successfully on localhost:8095
- Server shows "Starting CIDX Server on 127.0.0.1:8095"
- Documentation available at: http://127.0.0.1:8095/docs
- Server remains running and responsive

**Pass/Fail Criteria:**
- ✅ PASS: Server running, health endpoint responds
- ❌ FAIL: Server fails to start or becomes unresponsive

### Test 0.1.2: Verify Server Health
**Command to Execute:**
```bash
# Test server health endpoint
curl -s http://127.0.0.1:8095/health
```

**Expected Results:**
- Returns HTTP 403 Forbidden (requires authentication)
- OR Returns health data if public endpoint
- Server responds within reasonable time (<1 second)

**Pass/Fail Criteria:**
- ✅ PASS: Server responds (403 or health data)
- ❌ FAIL: Connection refused or timeout

### Test 0.1.3: Verify Admin Credentials
**Command to Execute:**
```bash
# Test admin login
curl -X POST http://127.0.0.1:8095/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

**Expected Results:**
- Returns HTTP 200 with JWT token
- Response contains "access_token" field
- Token format is valid JWT

**Pass/Fail Criteria:**
- ✅ PASS: Login succeeds, valid token returned
- ❌ FAIL: Login fails or invalid response

### Test 0.1.4: Check Repository State
**Command to Execute:**
```bash
# Get token and check repositories
TOKEN=$(curl -s -X POST http://127.0.0.1:8095/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}' | jq -r '.access_token')

# List activated repositories
curl -s -X GET http://127.0.0.1:8095/api/repos \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Results:**
- Returns list of activated repositories
- May be empty array if no repositories activated yet
- HTTP 200 response code

**Pass/Fail Criteria:**
- ✅ PASS: API responds with repository list (empty or populated)
- ❌ FAIL: API error or invalid response

### Test 0.1.5: Index Code-Indexer Repository
**Command to Execute:**
```bash
# Index the code-indexer repository itself for testing
curl -s -X POST http://127.0.0.1:8095/api/admin/golden-repos \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "code-indexer-main",
    "git_url": "file:///home/jsbattig/Dev/code-indexer",
    "branch": "master",
    "description": "Code-indexer repository for remote mode testing"
  }'
```

**Expected Results:**
- Returns HTTP 202 with job ID for indexing
- Indexing job starts processing repository
- Repository contains ~237KB CLI file and extensive server code

**Pass/Fail Criteria:**
- ✅ PASS: Repository indexing job created successfully
- ❌ FAIL: Indexing fails or job not created

### Test 0.1.6: Verify Repository Indexing Completion
**Command to Execute:**
```bash
# Monitor indexing job completion
JOB_ID="<job_id_from_previous_test>"
curl -s -X GET "http://127.0.0.1:8095/api/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN"

# Test query against indexed repository
curl -s -X POST http://127.0.0.1:8095/api/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication", "limit": 3}'
```

**Expected Results:**
- Job status shows "completed"
- Query returns results from code-indexer repository
- Results include files like "server/auth/jwt_manager.py" or "cli.py"
- Results show relevance scores for authentication-related code

**Pass/Fail Criteria:**
- ✅ PASS: Repository indexed, queries return relevant code-indexer content
- ❌ FAIL: Indexing incomplete or queries return no results

## 📊 **Server Monitoring During Tests**

### Monitor Server Logs
Watch server output for:
- Authentication attempts (successful/failed)
- API endpoint calls and responses
- Error messages or warnings
- Performance metrics

### Expected Log Patterns
```
INFO:     127.0.0.1:xxxxx - "POST /auth/login HTTP/1.1" 200 OK
INFO:     127.0.0.1:xxxxx - "GET /api/repos HTTP/1.1" 200 OK
INFO:     127.0.0.1:xxxxx - "POST /api/query HTTP/1.1" 200 OK
```

## 🎯 **Acceptance Criteria**

- [ ] CIDX server starts and runs stably on localhost:8095
- [ ] Health endpoint responds appropriately
- [ ] Admin credentials (admin/admin) work for authentication
- [ ] Repository API endpoints are accessible
- [ ] Query API endpoint processes requests successfully
- [ ] Server logs show proper request/response patterns

## 📝 **Manual Testing Notes**

**Prerequisites:**
- Code-indexer development environment
- Port 8095 available (not in use)
- Python environment with code-indexer dependencies
- Network connectivity to localhost

**Server Setup Requirements:**
- Keep server running throughout all remote mode tests
- Monitor server logs for errors or performance issues
- Have server restart procedure ready if needed
- Ensure server data directory permissions are correct

**Troubleshooting:**
- If port 8095 in use: `lsof -i :8095` and kill process
- If permission errors: Check data directory permissions
- If startup fails: Check Python environment and dependencies

**Critical Success Factor:**
This story MUST pass before any other remote mode testing can begin. A working server is the foundation for all remote mode functionality.

[Conversation Reference: "Real Server Testing Environment with working server on localhost:8095"]