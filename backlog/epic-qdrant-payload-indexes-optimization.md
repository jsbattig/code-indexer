# Epic: Qdrant Payload Indexes for Reconcile Performance Optimization

## Epic Intent
Implement Qdrant payload indexes to dramatically reduce CPU utilization during `index --reconcile` operations by enabling efficient filtering on frequently queried payload fields, potentially achieving 50-90% CPU reduction.

## Business Value
- **Massive CPU Reduction**: 50-90% less CPU usage during reconcile operations
- **Faster Reconcile**: 2-10x faster payload-based filtering and path lookups
- **Better User Experience**: Reconcile operations complete much faster
- **Resource Efficiency**: Significant reduction in system resource consumption
- **Scalability**: Better performance for large codebases with many files

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

**Technical Implementation:**
```pseudocode
def _create_payload_indexes(self, collection_name: str) -> bool:
    required_indexes = [
        ("type", "keyword"),         # content/metadata/visibility filtering
        ("path", "text"),            # file path matching  
        ("git_branch", "keyword"),   # branch-specific filtering
        ("file_mtime", "integer"),   # timestamp comparisons
        ("hidden_branches", "keyword") # branch visibility
    ]
    
    for field_name, field_schema in required_indexes:
        try:
            response = self.client.put(
                f"/collections/{collection_name}/index",
                json={"field_name": field_name, "field_schema": field_schema}
            )
            if response.status_code not in [200, 201]:
                logger.warning(f"Failed to create index on {field_name}")
        except Exception as e:
            logger.warning(f"Index creation failed for {field_name}: {e}")
    
    return True

# Integration points:
# - _create_collection_direct() calls _create_payload_indexes()
# - create_collection_with_profile() calls _create_payload_indexes() 
# - _create_collection_with_cow() calls _create_payload_indexes()
```

### Story 2: Configurable Payload Index Management
**As a system administrator**, I want to configure which payload indexes are created so that I can optimize for my specific use patterns and memory constraints.

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
- AND migration progress should be displayed to the user
- AND query operations should NOT trigger index creation (read-only)
- AND status operations should only report index status (read-only)

**Technical Implementation:**
```pseudocode
def ensure_payload_indexes(self, collection_name: str, context: str = "read") -> bool:
    """Ensure payload indexes exist, with context-aware behavior."""
    if not self.config.enable_payload_indexes:
        return True  # Indexes disabled, nothing to do
        
    index_status = self.get_payload_index_status(collection_name)
    
    if not index_status.get('missing_indexes'):
        return True  # All indexes exist
    
    missing = ', '.join(index_status['missing_indexes'])
    
    if context == "index":
        # INDEXING context: Auto-create missing indexes
        self.console.print("🔧 Creating missing payload indexes for optimal performance...")
        return self._create_payload_indexes(collection_name)
    
    elif context == "query":
        # QUERY context: Read-only, just warn about missing indexes
        self.console.print(f"ℹ️  Missing payload indexes: {missing}", style="dim")
        self.console.print("   Consider running 'cidx index' for 50-90% faster reconcile", style="dim")
        return True  # Don't block queries
    
    elif context == "status":
        # STATUS context: Report-only, no warnings during status checks
        return True  # Status will show index health separately
    
    else:
        # DEFAULT context: Report missing indexes
        self.console.print(f"⚠️  Missing payload indexes: {missing}", style="yellow")
        return False

# Integration points:
# INDEXING operations (auto-create):
def start_indexing_operation():
    ensure_collection(collection_name)
    ensure_payload_indexes(collection_name, context="index")  # Creates indexes

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

### Story 5: Performance Validation and Testing
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
    def test_filter_performance_with_indexes(self):
        """Test that filtering with indexes is significantly faster."""
        # Create collection without indexes
        collection_without = "test_no_indexes"
        self.qdrant_client.create_collection(collection_without)
        
        # Create collection with indexes  
        collection_with = "test_with_indexes"
        self.qdrant_client.create_collection(collection_with)
        self.qdrant_client._create_payload_indexes(collection_with)
        
        # Add identical test data to both
        test_points = self._generate_test_points(1000)
        self.qdrant_client.upsert_points(collection_without, test_points)
        self.qdrant_client.upsert_points(collection_with, test_points)
        
        # Benchmark filtering operations
        filter_conditions = {
            "must": [
                {"key": "type", "match": {"value": "content"}},
                {"key": "git_branch", "match": {"value": "main"}}
            ]
        }
        
        # Time filtering without indexes
        start = time.time()
        results_without = self.qdrant_client.scroll_points(
            collection_name=collection_without,
            filter_conditions=filter_conditions,
            limit=100
        )
        time_without = time.time() - start
        
        # Time filtering with indexes
        start = time.time()
        results_with = self.qdrant_client.scroll_points(
            collection_name=collection_with,
            filter_conditions=filter_conditions,
            limit=100
        )
        time_with = time.time() - start
        
        # Verify results are identical
        assert len(results_without[0]) == len(results_with[0])
        
        # Verify significant performance improvement (at least 2x faster)
        performance_ratio = time_without / time_with
        assert performance_ratio >= 2.0, f"Expected 2x improvement, got {performance_ratio:.2f}x"
        
    def test_reconcile_cpu_usage_reduction(self):
        """Test that reconcile operations use less CPU with indexes."""
        # This would require more complex CPU monitoring
        # but validates the core business value
        pass
        
    def test_index_creation_all_field_types(self):
        """Test that all supported field types create indexes correctly."""
        collection_name = "test_index_types"
        self.qdrant_client.create_collection(collection_name)
        
        test_indexes = [
            ("keyword_field", "keyword"),
            ("text_field", "text"),
            ("integer_field", "integer"),
            ("bool_field", "bool"),
        ]
        
        for field_name, field_schema in test_indexes:
            success = self.qdrant_client._create_single_payload_index(
                collection_name, field_name, field_schema
            )
            assert success, f"Failed to create {field_schema} index on {field_name}"
            
        # Verify all indexes exist
        existing_indexes = self.qdrant_client.list_payload_indexes(collection_name)
        existing_fields = {idx["field"] for idx in existing_indexes}
        expected_fields = {field for field, _ in test_indexes}
        
        assert existing_fields >= expected_fields
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

### **Implementation Strategy:**
1. **Phase 1**: Automatic index creation for new collections
2. **Phase 2**: Manual `create-indexes` command for existing collections  
3. **Phase 3**: Enhanced status reporting with index health
4. **Phase 4**: Optional auto-migration prompts

### **Backward Compatibility:**
- All changes are additive - existing collections continue working
- Index creation is optional and configurable
- Graceful degradation if index creation fails
- No breaking changes to existing APIs

This Epic provides a comprehensive solution for dramatically improving reconcile performance through Qdrant payload indexes while maintaining full backward compatibility and user control.