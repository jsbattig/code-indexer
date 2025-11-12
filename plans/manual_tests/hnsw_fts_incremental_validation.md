# Manual Test Plan: HNSW and FTS Incremental Index Validation

**Purpose**: Validate that both HNSW (semantic) and FTS (full-text) indexes correctly perform incremental updates rather than full rebuilds when files are modified.

**Test Date**: _____________
**Tester**: _____________
**Result**: ⬜ PASS ⬜ FAIL

---

## Prerequisites

- [ ] CIDX installed and available in PATH
- [ ] VoyageAI API key configured (for embeddings)
- [ ] Clean test environment (no existing `.code-indexer` directories)
- [ ] DEBUG logging temporarily enabled (see Setup section)

---

## Setup: Enable DEBUG Logging

**Objective**: Add temporary DEBUG logs to verify full vs incremental code paths.

### 1. Add HNSW Index Logging

**File**: `src/code_indexer/services/hnsw_index_manager.py`

**Location 1** - Full Index Creation (in `build_index` or `create_index` method):
```python
logger.debug("🔨 FULL HNSW INDEX BUILD: Creating index from scratch with %d vectors", len(vectors))
```

**Location 2** - Incremental Update (in `update_index` or `add_vectors` method):
```python
logger.debug("⚡ INCREMENTAL HNSW UPDATE: Adding/updating %d vectors (total index size: %d)", len(new_vectors), current_index_size)
```

### 2. Add FTS Index Logging

**File**: `src/code_indexer/services/tantivy_index_manager.py`

**Location 1** - Full Index Creation (in `create_index` or initial build method):
```python
logger.debug("🔨 FULL FTS INDEX BUILD: Creating Tantivy index from scratch with %d documents", document_count)
```

**Location 2** - Incremental Update (in `update_documents` or `add_documents` method):
```python
logger.debug("⚡ INCREMENTAL FTS UPDATE: Adding/updating %d documents (total index: %d)", len(modified_docs), total_docs)
```

### 3. Enable DEBUG Logging Output

Set environment variable:
```bash
export CODE_INDEXER_LOG_LEVEL=DEBUG
```

Or modify `src/code_indexer/cli.py` to set root logger to DEBUG level temporarily.

---

## Test Scenario 1: Manual `cidx index` Command

### Phase 1: Initial Full Index

**Step 1.1**: Create test repository
```bash
mkdir -p ~/.tmp/hnsw_fts_test
cd ~/.tmp/hnsw_fts_test
git init
```

**Step 1.2**: Create initial test files (10-20 Python files)
```bash
# Create 15 Python files with generic content
for i in {1..15}; do
cat > file_${i}.py << 'EOF'
"""Module for data processing utilities."""

def process_data(input_data):
    """Process input data and return results."""
    result = []
    for item in input_data:
        processed = transform_item(item)
        result.append(processed)
    return result

def transform_item(item):
    """Transform individual item."""
    return item.upper()

def validate_data(data):
    """Validate data structure."""
    if not isinstance(data, list):
        raise ValueError("Data must be a list")
    return True
EOF
done

git add .
git commit -m "Initial commit"
```

**Expected Result**: 15 Python files created and committed.

**Step 1.3**: Initialize CIDX with FTS enabled
```bash
cidx init --embedding-provider voyageai --fts
```

**Expected Result**:
- `.code-indexer/config.json` created
- FTS enabled in config

**Step 1.4**: Start CIDX daemon
```bash
cidx start
```

**Expected Result**:
- Qdrant container started
- Daemon ready

**Step 1.5**: Run full index with DEBUG logging
```bash
cidx index 2>&1 | tee full_index.log
```

**Expected Result**:
- Progress bar shows indexing 15 files
- Index completes successfully

**Step 1.6**: Inspect logs for FULL INDEX markers
```bash
grep "🔨 FULL" full_index.log
```

**Expected Output**:
```
🔨 FULL HNSW INDEX BUILD: Creating index from scratch with 15 vectors
🔨 FULL FTS INDEX BUILD: Creating Tantivy index from scratch with 15 documents
```

✅ **Checkpoint 1**: Confirm both FULL index markers appear in logs.

---

### Phase 2: Query Initial Index

**Step 2.1**: Test HNSW semantic search
```bash
cidx query "data processing utilities" --limit 5 --quiet
```

**Expected Result**:
- Returns matches from initial 15 files
- Shows files containing "data processing" concepts

**Step 2.2**: Test FTS exact text search
```bash
cidx query "transform_item" --fts --limit 5 --quiet
```

**Expected Result**:
- Returns matches for exact function name "transform_item"
- Shows line numbers and snippets

✅ **Checkpoint 2**: Both search modes return results from initial corpus.

---

### Phase 3: Modify Files with Unique Markers

**Step 3.1**: Add unique content to 3 files
```bash
# Add unique semantic concept to file_1.py
cat >> file_1.py << 'EOF'

def quantum_entanglement_simulator():
    """Simulate quantum entanglement for particles."""
    particles = initialize_quantum_state()
    entangle_particles(particles)
    return measure_entanglement()
EOF

# Add unique FTS marker to file_2.py
cat >> file_2.py << 'EOF'

def UNIQUEMARKER_IncrementalTest_XYZ123():
    """Function with unique marker for FTS testing."""
    return "incremental_update_verified"
EOF

# Add both unique markers to file_3.py
cat >> file_3.py << 'EOF'

def blockchain_consensus_algorithm():
    """Implement blockchain consensus using proof of stake."""
    validators = select_validators()
    return achieve_consensus(validators)

def UNIQUEMARKER_FullTextSearch_ABC456():
    """Another unique marker for FTS validation."""
    return "fts_incremental_works"
EOF

git add .
git commit -m "Add unique markers for incremental test"
```

**Expected Result**: 3 files modified with unique searchable content.

---

### Phase 4: Incremental Index Update

**Step 4.1**: Run incremental index with DEBUG logging
```bash
cidx index 2>&1 | tee incremental_index.log
```

**Expected Result**:
- Progress bar shows processing (should be faster than full index)
- Index completes successfully

**Step 4.2**: Inspect logs for INCREMENTAL UPDATE markers
```bash
grep "⚡ INCREMENTAL" incremental_index.log
```

**Expected Output**:
```
⚡ INCREMENTAL HNSW UPDATE: Adding/updating 3 vectors (total index size: 15)
⚡ INCREMENTAL FTS UPDATE: Adding/updating 3 documents (total index: 15)
```

✅ **Checkpoint 3**: Confirm both INCREMENTAL update markers appear (NOT FULL INDEX markers).

**Step 4.3**: Verify NO full rebuild occurred
```bash
grep "🔨 FULL" incremental_index.log
```

**Expected Output**: (empty - no full rebuild should occur)

✅ **Checkpoint 4**: Confirm NO full index markers in incremental run.

---

### Phase 5: Query Updated Index

**Step 5.1**: Test HNSW search for new semantic content
```bash
cidx query "quantum entanglement simulation" --limit 5 --quiet
```

**Expected Result**:
- Returns `file_1.py` with high relevance score
- Shows the new `quantum_entanglement_simulator` function

**Step 5.2**: Test HNSW search for blockchain content
```bash
cidx query "blockchain consensus proof of stake" --limit 5 --quiet
```

**Expected Result**:
- Returns `file_3.py` with high relevance score
- Shows the new `blockchain_consensus_algorithm` function

**Step 5.3**: Test FTS search for unique marker 1
```bash
cidx query "UNIQUEMARKER_IncrementalTest_XYZ123" --fts --limit 5 --quiet
```

**Expected Result**:
- Returns `file_2.py` with exact match
- Shows the unique function name in snippet

**Step 5.4**: Test FTS search for unique marker 2
```bash
cidx query "UNIQUEMARKER_FullTextSearch_ABC456" --fts --limit 5 --quiet
```

**Expected Result**:
- Returns `file_3.py` with exact match
- Shows the unique function name in snippet

✅ **Checkpoint 5**: All unique content (both HNSW and FTS) is searchable after incremental update.

---

### Phase 6: Cleanup
```bash
cidx stop
cd ~
rm -rf ~/.tmp/hnsw_fts_test
```

---

## Test Scenario 2: `cidx watch` Mode with Live Updates

### Phase 1: Initial Setup and Full Index

**Step 1.1**: Create test repository
```bash
mkdir -p ~/.tmp/hnsw_fts_watch_test
cd ~/.tmp/hnsw_fts_watch_test
git init
```

**Step 1.2**: Create initial test files (10 Python files)
```bash
# Create 10 Python files with generic content
for i in {1..10}; do
cat > watch_file_${i}.py << 'EOF'
"""Module for API endpoint handlers."""

def handle_request(request):
    """Handle incoming HTTP request."""
    validate_request(request)
    response = process_request(request)
    return response

def validate_request(request):
    """Validate request structure."""
    if not request.method in ['GET', 'POST']:
        raise ValueError("Invalid method")
    return True
EOF
done

git add .
git commit -m "Initial commit for watch test"
```

**Expected Result**: 10 Python files created and committed.

**Step 1.3**: Initialize CIDX with FTS
```bash
cidx init --embedding-provider voyageai --fts
```

**Step 1.4**: Start CIDX daemon
```bash
cidx start
```

**Step 1.5**: Run initial full index
```bash
cidx index 2>&1 | tee watch_full_index.log
```

**Step 1.6**: Verify FULL INDEX markers
```bash
grep "🔨 FULL" watch_full_index.log
```

**Expected Output**:
```
🔨 FULL HNSW INDEX BUILD: Creating index from scratch with 10 vectors
🔨 FULL FTS INDEX BUILD: Creating Tantivy index from scratch with 10 documents
```

✅ **Checkpoint 1**: Full index completed with proper markers.

---

### Phase 2: Start Watch Mode

**Step 2.1**: Start watch mode in background with logging
```bash
cidx watch 2>&1 | tee watch_mode.log &
WATCH_PID=$!
echo "Watch mode started with PID: $WATCH_PID"
```

**Expected Result**:
- Watch mode starts monitoring file changes
- Process runs in background

**Step 2.2**: Wait for watch mode to initialize (5 seconds)
```bash
sleep 5
```

---

### Phase 3: Query Initial Index

**Step 3.1**: Test HNSW search (should work with existing content)
```bash
cidx query "API endpoint handlers" --limit 5 --quiet
```

**Expected Result**: Returns matches from initial 10 files.

**Step 3.2**: Test FTS search (should work with existing content)
```bash
cidx query "handle_request" --fts --limit 5 --quiet
```

**Expected Result**: Returns matches for "handle_request" function.

✅ **Checkpoint 2**: Initial searches work before modifications.

---

### Phase 4: Modify Files While Watch Mode Running

**Step 4.1**: Add unique content to file while watch is active
```bash
cat >> watch_file_1.py << 'EOF'

def kubernetes_pod_orchestration():
    """Orchestrate Kubernetes pods for microservices deployment."""
    pods = create_pod_definitions()
    deploy_pods(pods)
    return monitor_pod_health()
EOF

git add watch_file_1.py
git commit -m "Add kubernetes orchestration"
```

**Step 4.2**: Add unique FTS marker to another file
```bash
cat >> watch_file_2.py << 'EOF'

def WATCHMODE_UniqueMarker_LIVE789():
    """Unique function marker for watch mode FTS testing."""
    return "watch_mode_incremental_verified"
EOF

git add watch_file_2.py
git commit -m "Add unique FTS marker"
```

**Step 4.3**: Wait for watch mode to detect and process changes (10 seconds)
```bash
sleep 10
```

**Expected Result**:
- Watch mode detects file modifications
- Triggers incremental index update automatically

---

### Phase 5: Verify Incremental Updates in Watch Mode

**Step 5.1**: Inspect watch mode logs for INCREMENTAL markers
```bash
grep "⚡ INCREMENTAL" watch_mode.log
```

**Expected Output**:
```
⚡ INCREMENTAL HNSW UPDATE: Adding/updating 2 vectors (total index size: 10)
⚡ INCREMENTAL FTS UPDATE: Adding/updating 2 documents (total index: 10)
```

✅ **Checkpoint 3**: Watch mode triggered incremental updates (NOT full rebuild).

**Step 5.2**: Verify NO full rebuild in watch mode
```bash
grep "🔨 FULL" watch_mode.log | grep -v "Initial"
```

**Expected Output**: (empty - no full rebuilds after initial index)

✅ **Checkpoint 4**: Watch mode did NOT trigger full index rebuild.

---

### Phase 6: Query Updated Index (Live)

**Step 6.1**: Test HNSW search for new Kubernetes content
```bash
cidx query "kubernetes pod orchestration microservices" --limit 5 --quiet
```

**Expected Result**:
- Returns `watch_file_1.py` with high relevance
- Shows the new `kubernetes_pod_orchestration` function

**Step 6.2**: Test FTS search for unique watch mode marker
```bash
cidx query "WATCHMODE_UniqueMarker_LIVE789" --fts --limit 5 --quiet
```

**Expected Result**:
- Returns `watch_file_2.py` with exact match
- Shows the unique function name in snippet

✅ **Checkpoint 5**: Live updates are searchable immediately after watch mode processes them.

---

### Phase 7: Stop Watch Mode and Cleanup

**Step 7.1**: Stop watch mode
```bash
kill $WATCH_PID
```

**Step 7.2**: Verify watch mode logs one final time
```bash
cat watch_mode.log
```

**Step 7.3**: Cleanup
```bash
cidx stop
cd ~
rm -rf ~/.tmp/hnsw_fts_watch_test
```

---

## Success Criteria

### Scenario 1 (Manual `cidx index`)
- ✅ Initial index shows FULL BUILD markers for both HNSW and FTS
- ✅ Incremental index shows INCREMENTAL UPDATE markers for both HNSW and FTS
- ✅ Incremental index does NOT show FULL BUILD markers
- ✅ New unique content (semantic and exact text) is searchable after incremental update
- ✅ Query results return correct files with new content

### Scenario 2 (`cidx watch` mode)
- ✅ Initial index shows FULL BUILD markers
- ✅ Watch mode detects file changes automatically
- ✅ Watch mode triggers INCREMENTAL UPDATE markers (not full rebuild)
- ✅ Watch mode does NOT trigger FULL BUILD after initial index
- ✅ New content is immediately searchable while watch mode runs
- ✅ Query results return correct files with live updates

---

## Failure Scenarios

### If FULL BUILD markers appear during incremental updates:
- **Issue**: Index is rebuilding from scratch instead of incremental update
- **Impact**: Performance degradation, unnecessary work
- **Action**: Investigate why incremental update code path is not triggered

### If new content is NOT searchable after updates:
- **Issue**: Index update failed or incomplete
- **Action**: Check for errors in logs, verify index file modifications

### If watch mode does NOT detect changes:
- **Issue**: File watching mechanism broken
- **Action**: Check inotify/filesystem events, verify git commit triggers detection

---

## Notes

- Remove DEBUG logging after manual test completion
- Performance comparison: Incremental should be significantly faster than full rebuild
- Watch mode should have minimal latency between file change and searchability (<30 seconds)
- Both HNSW and FTS indexes must update incrementally in parallel

---

## Test Evidence

Attach the following logs to test results:
1. `full_index.log` - Initial full index with FULL BUILD markers
2. `incremental_index.log` - Incremental update with INCREMENTAL markers
3. `watch_full_index.log` - Watch mode initial full index
4. `watch_mode.log` - Watch mode with live incremental updates
5. Screenshots of query results showing unique content matches
