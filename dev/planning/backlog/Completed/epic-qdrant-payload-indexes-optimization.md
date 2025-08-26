# Epic: Qdrant Payload Indexes for Performance Optimization

## Epic Intent
Implement Qdrant payload indexes to dramatically reduce CPU utilization during filtering operations by enabling efficient lookups on frequently queried payload fields, potentially achieving 50-90% CPU reduction for reconcile operations and significant performance improvements across all operations using payload filtering.

## Business Value
- **Massive CPU Reduction**: 50-90% less CPU usage during reconcile operations
- **Faster Operations**: 2-10x faster payload-based filtering across all operations (query, reconcile, branch operations)
- **Better User Experience**: All filtering operations complete much faster
- **Resource Efficiency**: Significant reduction in system resource consumption
- **Scalability**: Better performance for large codebases with many files
- **Improved Semantic Search**: Faster path and language filtering during `cidx query` operations
- **Enhanced Git Operations**: Faster branch visibility filtering and branch-specific operations

## User Stories

### Story 1: Automatic Payload Index Creation During Collection Setup
**As a developer**, I want payload indexes created automatically when collections are created so that I get optimal performance without manual intervention.

**Acceptance Criteria:**
- GIVEN a new Qdrant collection is being created
- WHEN `_create_collection_direct` or `_create_collection_with_cow` is called
- THEN payload indexes should be created automatically for key fields
- AND indexes should be created for: `type`, `path`, `git_branch`, `file_mtime`, `hidden_branches`
- AND index creation failures should be logged as warnings but not fail collection creation
- AND index creation should use appropriate field schemas (keyword, text, integer)
- AND index creation progress should be displayed to the user during collection setup
- AND users should see which indexes are being created and their status

**Technical Implementation:**
```pseudocode
def _create_payload_indexes_with_retry(self, collection_name: str) -> bool:
    """Create payload indexes with retry logic and user feedback for single-user reliability."""
    required_indexes = [
        ("type", "keyword"),         # content/metadata/visibility filtering
        ("path", "text"),            # file path matching  
        ("git_branch", "keyword"),   # branch-specific filtering
        ("file_mtime", "integer"),   # timestamp comparisons
        ("hidden_branches", "keyword") # branch visibility
    ]
    
    self.console.print("🔧 Setting up payload indexes for optimal query performance...")
    success_count = 0
    
    for field_name, field_schema in required_indexes:
        self.console.print(f"   • Creating index for '{field_name}' field ({field_schema} type)...")
        
        # Retry logic for network/service issues (single-user, no concurrency concerns)
        index_created = False
        for attempt in range(3):
            try:
                response = self.client.put(
                    f"/collections/{collection_name}/index",
                    json={"field_name": field_name, "field_schema": field_schema}
                )
                if response.status_code in [200, 201]:
                    success_count += 1
                    index_created = True
                    self.console.print(f"   ✅ Index for '{field_name}' created successfully")
                    break
                elif response.status_code == 409:  # Index already exists
                    success_count += 1
                    index_created = True
                    self.console.print(f"   ✅ Index for '{field_name}' already exists")
                    break
                else:
                    if attempt < 2:  # Not the last attempt
                        self.console.print(f"   ⚠️  Attempt {attempt + 1} failed (HTTP {response.status_code}), retrying...")
                    else:
                        self.console.print(f"   ❌ Failed to create index for '{field_name}' after 3 attempts (HTTP {response.status_code})")
                        logger.warning(f"Failed to create index on {field_name}: HTTP {response.status_code}")
            except Exception as e:
                if attempt < 2:  # Not the last attempt
                    self.console.print(f"   ⚠️  Attempt {attempt + 1} failed ({str(e)[:50]}...), retrying in {2 ** attempt}s...")
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                else:
                    self.console.print(f"   ❌ Failed to create index for '{field_name}' after 3 attempts: {str(e)[:100]}")
                    logger.warning(f"Index creation failed for {field_name}: {e}")
        
        if not index_created:
            self.console.print(f"   ⚠️  Index creation failed for '{field_name}' - queries may be slower")
    
    # Final status with user-friendly summary
    if success_count == len(required_indexes):
        self.console.print(f"   📊 Successfully created all {success_count} payload indexes")
        logger.info(f"Successfully created {success_count} payload indexes for collection {collection_name}")
        return True
    else:
        self.console.print(f"   📊 Created {success_count}/{len(required_indexes)} payload indexes ({len(required_indexes) - success_count} failed)")
        logger.warning(f"Created {success_count}/{len(required_indexes)} payload indexes for collection {collection_name}")
        return success_count > 0  # Partial success is acceptable

# Integration points:
# - _create_collection_direct() calls _create_payload_indexes_with_retry()
# - create_collection_with_profile() calls _create_payload_indexes_with_retry() 
# - _create_collection_with_cow() calls _create_payload_indexes_with_retry()
```

### Story 2: Configurable Payload Index Management
**As a developer**, I want to configure which payload indexes are created so that I can optimize for my specific use patterns and memory constraints.

**Acceptance Criteria:**
- GIVEN QdrantConfig in config.py
- WHEN I configure payload index settings
- THEN I should be able to enable/disable payload indexes entirely
- AND I should be able to customize which fields are indexed
- AND configuration should include memory impact warnings
- AND backward compatibility should be maintained for existing configurations

**Technical Implementation:**
```pseudocode
class QdrantConfig(BaseModel):
    # Existing fields...
    
    enable_payload_indexes: bool = Field(
        default=True,
        description="Enable payload indexes for faster filtering (uses 100-300MB additional RAM)"
    )
    
    payload_indexes: List[Tuple[str, str]] = Field(
        default=[
            ("type", "keyword"),
            ("path", "text"), 
            ("git_branch", "keyword"),
            ("file_mtime", "integer"),
            ("hidden_branches", "keyword"),
        ],
        description="List of (field_name, field_schema) tuples for payload indexes"
    )
    
    @field_validator("payload_indexes")
    @classmethod
    def validate_payload_indexes(cls, v):
        valid_schemas = {"keyword", "text", "integer", "geo", "bool"}
        for field_name, field_schema in v:
            if field_schema not in valid_schemas:
                raise ValueError(f"Invalid field_schema '{field_schema}' for field '{field_name}'")
        return v
```

### Story 3: Index Health Monitoring and Status Reporting
**As a developer**, I want to see the status of payload indexes so that I can verify they're working and monitor their health.

**Acceptance Criteria:**
- GIVEN the `cidx status` command
- WHEN I run status checks
- THEN I should see payload index information in the output
- AND status should show which indexes exist and are healthy
- AND status should show missing indexes if any are expected
- AND status should include memory usage estimates for indexes
- AND status should be displayed in a clear, readable format

**Technical Implementation:**
```pseudocode
def get_payload_index_status(self, collection_name: str) -> Dict[str, Any]:
    """Get detailed status of payload indexes."""
    try:
        existing_indexes = self.list_payload_indexes(collection_name)
        expected_indexes = self.config.payload_indexes if self.config.enable_payload_indexes else []
        
        existing_fields = {idx["field"] for idx in existing_indexes}
        expected_fields = {field for field, _ in expected_indexes}
        
        return {
            "indexes_enabled": self.config.enable_payload_indexes,
            "total_indexes": len(existing_indexes),
            "expected_indexes": len(expected_indexes),
            "missing_indexes": list(expected_fields - existing_fields),
            "extra_indexes": list(existing_fields - expected_fields),
            "healthy": len(existing_indexes) >= len(expected_indexes) and not bool(expected_fields - existing_fields),
            "estimated_memory_mb": self._estimate_index_memory_usage(existing_indexes),
            "indexes": existing_indexes
        }
    except Exception as e:
        return {"error": str(e), "healthy": False}

# Integration in status command:
def status_command():
    # ... existing status logic ...
    
    # Add payload index status
    if collection_exists:
        index_status = qdrant_client.get_payload_index_status(collection_name)
        if index_status.get("healthy", False):
            console.print("📊 Payload Indexes: ✅ Healthy", style="green")
            console.print(f"   • {index_status['total_indexes']} indexes active")
            console.print(f"   • ~{index_status['estimated_memory_mb']}MB memory usage")
        else:
            console.print("📊 Payload Indexes: ⚠️  Issues detected", style="yellow")
            if index_status.get("missing_indexes"):
                console.print(f"   • Missing: {', '.join(index_status['missing_indexes'])}")
```

### Story 4: Migration Support for Existing Collections
**As a user with existing collections**, I want my collections to automatically get payload indexes so that I benefit from performance improvements without manual intervention.

**Acceptance Criteria:**
- GIVEN an existing collection without payload indexes
- WHEN I run the `cidx index` command
- THEN the system should detect missing indexes
- AND the system should create missing indexes automatically
- AND migration progress should be displayed to the user with detailed feedback per index
- AND retry attempts should be shown with clear status messages
- AND final summary should show success/failure count for transparency
- AND query operations should NOT trigger index creation (read-only)
- AND status operations should only report index status (read-only)

**Technical Implementation:**
```pseudocode
def ensure_payload_indexes(self, collection_name: str, context: str = "read") -> bool:
    """Ensure payload indexes exist, with context-aware behavior (single-user optimized)."""
    if not self.config.enable_payload_indexes:
        return True  # Indexes disabled, nothing to do
        
    index_status = self.get_payload_index_status(collection_name)
    
    if not index_status.get('missing_indexes'):
        return True  # All indexes exist
    
    missing = ', '.join(index_status['missing_indexes'])
    
    if context == "index":
        # INDEXING context: Auto-create missing indexes with retry logic
        self.console.print("🔧 Creating missing payload indexes for optimal performance...")
        success = self._create_missing_indexes_with_detailed_feedback(collection_name, index_status['missing_indexes'])
        if success:
            self.console.print("✅ All payload indexes created successfully")
        else:
            self.console.print("⚠️  Some payload indexes failed to create (performance may be degraded)")
        return success
    
    elif context == "query":
        # QUERY context: Read-only, just inform about missing indexes
        self.console.print(f"ℹ️  Missing payload indexes: {missing}", style="dim")
        self.console.print("   Consider running 'cidx index' for 50-90% faster operations", style="dim")
        return True  # Don't block queries
    
    elif context == "status":
        # STATUS context: Report-only, no warnings during status checks
        return True  # Status will show index health separately
    
    else:
        # DEFAULT context: Report missing indexes
        self.console.print(f"⚠️  Missing payload indexes: {missing}", style="yellow")
        return False

def _create_missing_indexes_with_detailed_feedback(self, collection_name: str, missing_fields: List[str]) -> bool:
    """Create only missing indexes with retry logic and detailed user feedback."""
    field_schema_map = dict(self.config.payload_indexes)
    success_count = 0
    
    for field_name in missing_fields:
        field_schema = field_schema_map.get(field_name)
        if not field_schema:
            self.console.print(f"   ⚠️  No schema configured for field '{field_name}', skipping")
            continue
            
        self.console.print(f"   • Creating index for '{field_name}' field ({field_schema} type)...")
        
        # Retry logic for each missing index with progress feedback
        index_created = False
        for attempt in range(3):
            try:
                response = self.client.put(
                    f"/collections/{collection_name}/index",
                    json={"field_name": field_name, "field_schema": field_schema}
                )
                if response.status_code in [200, 201]:
                    success_count += 1
                    index_created = True
                    self.console.print(f"   ✅ Index for '{field_name}' created successfully")
                    break
                elif response.status_code == 409:  # Index already exists
                    success_count += 1
                    index_created = True
                    self.console.print(f"   ✅ Index for '{field_name}' already exists")
                    break
                else:
                    if attempt < 2:  # Not the last attempt
                        self.console.print(f"   ⚠️  Attempt {attempt + 1} failed (HTTP {response.status_code}), retrying...")
                    else:
                        self.console.print(f"   ❌ Failed to create index for '{field_name}' after 3 attempts (HTTP {response.status_code})")
            except Exception as e:
                if attempt < 2:  # Not the last attempt
                    self.console.print(f"   ⚠️  Attempt {attempt + 1} failed ({str(e)[:50]}...), retrying in {2 ** attempt}s...")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.console.print(f"   ❌ Failed to create index for '{field_name}' after 3 attempts: {str(e)[:100]}")
        
        if not index_created:
            self.console.print(f"   ⚠️  Index creation failed for '{field_name}' - queries may be slower")
    
    # Summary feedback
    if success_count == len(missing_fields):
        self.console.print(f"   📊 Successfully created {success_count}/{len(missing_fields)} payload indexes")
    else:
        self.console.print(f"   📊 Created {success_count}/{len(missing_fields)} payload indexes ({len(missing_fields) - success_count} failed)")
    
    return success_count == len(missing_fields)

# Integration points:
# INDEXING operations (auto-create):
def start_indexing_operation():
    ensure_collection(collection_name)
    ensure_payload_indexes(collection_name, context="index")  # Creates indexes with retry

# QUERY operations (read-only):
def query_operation():
    ensure_collection(collection_name) 
    ensure_payload_indexes(collection_name, context="query")  # No index creation

# STATUS operations (silent):
def status_operation():
    if collection_exists:
        ensure_payload_indexes(collection_name, context="status")  # No warnings
        # Status shows index health separately via get_payload_index_status()
```

### Story 5: Index Recovery and Management
**As a developer**, I want to be able to rebuild corrupted or missing payload indexes so that I can recover from index-related issues and maintain optimal performance.

**Acceptance Criteria:**
- GIVEN a collection with corrupted or missing indexes
- WHEN I run `cidx reindex --rebuild-indexes` command
- THEN the system should drop existing indexes and recreate them
- AND the system should provide clear feedback about the rebuild process
- AND the system should verify index health after rebuild
- AND the system should handle rebuild failures gracefully
- AND the command should work for both git-aware and non-git-aware projects

**Technical Implementation:**
```pseudocode
def rebuild_payload_indexes(self, collection_name: str) -> bool:
    """Rebuild all payload indexes from scratch for reliability."""
    if not self.config.enable_payload_indexes:
        self.console.print("Payload indexes are disabled in configuration")
        return True
    
    self.console.print("🔧 Rebuilding payload indexes...")
    
    try:
        # Step 1: Remove existing indexes
        existing_indexes = self.list_payload_indexes(collection_name)
        for index in existing_indexes:
            self._drop_payload_index(collection_name, index["field"])
        
        # Step 2: Create fresh indexes with retry logic
        success = self._create_payload_indexes_with_retry(collection_name)
        
        if success:
            # Step 3: Verify health
            index_status = self.get_payload_index_status(collection_name)
            if index_status["healthy"]:
                self.console.print("✅ Payload indexes rebuilt successfully")
                return True
            else:
                self.console.print("⚠️  Index rebuild completed but health check failed")
                return False
        else:
            self.console.print("❌ Failed to rebuild some indexes")
            return False
            
    except Exception as e:
        self.console.print(f"❌ Index rebuild failed: {e}")
        return False

def _drop_payload_index(self, collection_name: str, field_name: str) -> bool:
    """Drop a single payload index."""
    try:
        response = self.client.delete(f"/collections/{collection_name}/index/{field_name}")
        return response.status_code in [200, 204, 404]  # Success or already deleted
    except Exception:
        return False

# CLI integration:
@click.option(
    "--rebuild-indexes",
    is_flag=True,
    help="Rebuild payload indexes for optimal performance"
)
def reindex_command(rebuild_indexes: bool):
    """Enhanced reindex command with index management."""
    if rebuild_indexes:
        if qdrant_client.rebuild_payload_indexes(collection_name):
            console.print("Index rebuild completed successfully")
        else:
            console.print("Index rebuild failed - check logs for details")
            sys.exit(1)
    else:
        # Regular reindexing logic
        perform_regular_reindex()
```

### Story 6: Performance Validation and Testing
**As a quality assurance engineer**, I want comprehensive tests that validate payload index performance improvements so that we can verify the optimization actually works.

**Acceptance Criteria:**
- GIVEN a test collection with and without payload indexes
- WHEN performance tests are executed
- THEN tests should measure query performance differences
- AND tests should validate CPU usage reduction during filtering operations
- AND tests should verify index creation and management functionality
- AND tests should include realistic data sets for meaningful benchmarks
- AND tests should validate all index field types work correctly

**Technical Implementation:**
```pseudocode
class TestPayloadIndexPerformance:
    def test_filter_performance_multiple_scales(self):
        """Test that filtering with indexes is significantly faster across different data sizes."""
        test_sizes = [1_000, 10_000, 100_000]  # Realistic dataset sizes
        
        for size in test_sizes:
            # Create collection without indexes
            collection_without = f"test_no_indexes_{size}"
            self.qdrant_client.create_collection(collection_without)
            
            # Create collection with indexes  
            collection_with = f"test_with_indexes_{size}"
            self.qdrant_client.create_collection(collection_with)
            self.qdrant_client._create_payload_indexes_with_retry(collection_with)
            
            # Add identical realistic test data
            test_points = self._generate_realistic_test_points(size)
            self.qdrant_client.upsert_points(collection_without, test_points)
            self.qdrant_client.upsert_points(collection_with, test_points)
            
            # Test multiple filter patterns
            filter_patterns = [
                # Single field filters
                {"must": [{"key": "type", "match": {"value": "content"}}]},
                {"must": [{"key": "path", "match": {"text": "src/"}}]},
                {"must": [{"key": "git_branch", "match": {"value": "main"}}]},
                # Compound filters (common in reconcile operations)
                {"must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "git_branch", "match": {"value": "main"}}
                ]},
                # Complex filters with multiple conditions
                {"must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "path", "match": {"text": ".py"}},
                    {"key": "git_branch", "match": {"value": "main"}}
                ]}
            ]
            
            for filter_conditions in filter_patterns:
                # Benchmark without indexes
                start = time.time()
                results_without = self.qdrant_client.scroll_points(
                    collection_name=collection_without,
                    filter_conditions=filter_conditions,
                    limit=100
                )
                time_without = time.time() - start
                
                # Benchmark with indexes
                start = time.time()
                results_with = self.qdrant_client.scroll_points(
                    collection_name=collection_with,
                    filter_conditions=filter_conditions,
                    limit=100
                )
                time_with = time.time() - start
                
                # Verify results are identical
                assert len(results_without[0]) == len(results_with[0])
                
                # Verify performance improvement scales with data size
                expected_ratio = 2.0 if size <= 10_000 else 5.0  # Higher ratios for larger datasets
                performance_ratio = time_without / time_with
                assert performance_ratio >= expected_ratio, \
                    f"Size {size}: Expected {expected_ratio}x improvement, got {performance_ratio:.2f}x"
    
    def test_index_creation_reliability(self):
        """Test index creation with retry logic and error handling."""
        collection_name = "test_index_reliability"
        self.qdrant_client.create_collection(collection_name)
        
        # Test successful index creation
        success = self.qdrant_client._create_payload_indexes_with_retry(collection_name)
        assert success, "Index creation should succeed"
        
        # Test idempotent behavior (creating indexes that already exist)
        success_again = self.qdrant_client._create_payload_indexes_with_retry(collection_name)
        assert success_again, "Index creation should be idempotent"
        
        # Verify all expected indexes exist
        existing_indexes = self.qdrant_client.list_payload_indexes(collection_name)
        existing_fields = {idx["field"] for idx in existing_indexes}
        expected_fields = {"type", "path", "git_branch", "file_mtime", "hidden_branches"}
        
        assert existing_fields >= expected_fields, f"Missing indexes: {expected_fields - existing_fields}"
        
    def test_index_health_monitoring(self):
        """Test index status reporting and health checks."""
        collection_name = "test_index_health"
        self.qdrant_client.create_collection(collection_name)
        
        # Test status with no indexes
        status = self.qdrant_client.get_payload_index_status(collection_name)
        assert not status["healthy"], "Should report unhealthy when indexes missing"
        assert len(status["missing_indexes"]) == 5, "Should report all 5 missing indexes"
        
        # Create indexes
        self.qdrant_client._create_payload_indexes_with_retry(collection_name)
        
        # Test status with all indexes
        status = self.qdrant_client.get_payload_index_status(collection_name)
        assert status["healthy"], "Should report healthy when all indexes exist"
        assert len(status["missing_indexes"]) == 0, "Should report no missing indexes"
        assert status["total_indexes"] >= 5, "Should have at least 5 indexes"
        
    def _generate_realistic_test_points(self, count: int) -> List[Dict]:
        """Generate realistic test data that mimics actual code indexing payloads."""
        points = []
        file_extensions = [".py", ".js", ".ts", ".java", ".cpp", ".go", ".rs"]
        branches = ["main", "develop", "feature/auth", "bugfix/parser"]
        
        for i in range(count):
            ext = file_extensions[i % len(file_extensions)]
            branch = branches[i % len(branches)]
            
            points.append({
                "id": str(i),
                "vector": [0.1] * 1536,  # Realistic embedding size
                "payload": {
                    "type": "content" if i % 10 != 0 else "metadata",
                    "path": f"src/module_{i // 100}/file_{i}{ext}",
                    "git_branch": branch,
                    "file_mtime": int(time.time()) - (i * 3600),  # Hours ago
                    "hidden_branches": [b for b in branches if b != branch][:2],
                    "language": ext[1:],  # Remove dot
                    "content": f"Function definition for item {i}"
                }
            })
        return points
```

## Implementation Notes

### **Memory Usage Estimates:**
- **`type` field**: ~1-5MB (few distinct values: content, metadata, visibility)
- **`path` field**: ~50-200MB (depends on number of unique file paths)
- **`git_branch` field**: ~1-10MB (limited number of branches)
- **`file_mtime` field**: ~20-50MB (integer timestamps)
- **`hidden_branches` field**: ~10-30MB (branch lists per file)
- **Total**: ~100-300MB additional RAM usage

### **Performance Benefits:**
- **CPU Reduction**: 50-90% during reconcile operations
- **Query Speed**: 2-10x faster for payload-filtered queries  
- **Specific Improvements**:
  - `type="content"` filtering: ~95% faster
  - Path lookups: ~90% faster
  - Branch filtering: ~80% faster
  - Timestamp comparisons: ~85% faster

### **Implementation Strategy (Single-User Optimized):**
1. **Phase 1**: Automatic index creation for new collections with retry logic
2. **Phase 2**: Migration support for existing collections during indexing operations
3. **Phase 3**: Enhanced status reporting with index health monitoring
4. **Phase 4**: Manual index rebuild capability for recovery scenarios

### **Single-User Architecture Benefits:**
- **Simplified Design**: No distributed locking or concurrent access concerns
- **Reliable Recovery**: User-controlled index rebuilding without coordination overhead
- **Straightforward Implementation**: Existing `IndexingLock` prevents process conflicts
- **Clear Error Handling**: Direct user feedback without multi-process complexity
- **Predictable Behavior**: Sequential operations eliminate race conditions

### **Backward Compatibility:**
- All changes are additive - existing collections continue working
- Index creation is optional and configurable
- Graceful degradation if index creation fails
- No breaking changes to existing APIs
- Partial index creation acceptable (performance degradation but functional)

### **Risk Mitigation (Single-User Context):**
- **Network/Service Issues**: Retry logic with exponential backoff
- **Partial Failures**: Continue operation with degraded performance
- **Memory Constraints**: Clear memory usage reporting and warnings
- **Qdrant Version Compatibility**: Graceful handling of unsupported features
- **User Recovery**: Manual rebuild command for corrupted indexes

This Epic provides a comprehensive solution for dramatically improving performance through Qdrant payload indexes while being optimized for single-user scenarios and maintaining full backward compatibility with user-controlled recovery options.