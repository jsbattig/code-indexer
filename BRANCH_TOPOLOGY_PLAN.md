# Branch-Topology-Aware Smart Indexing Implementation Plan

## Problem Statement

Current git-aware indexing reprocesses ALL files on branch changes, causing performance issues for large codebases. We need intelligent incremental indexing that understands:
- Branch topology and relationships
- Incremental changes between branches
- Staged and unstaged files
- Performance optimization for large repositories

## Solution Architecture

### 1. Enhanced Git Topology Service

```python
class GitTopologyService:
    """Advanced git topology analysis for smart incremental indexing."""
    
    def analyze_branch_change(self, old_branch: str, new_branch: str) -> BranchChangeAnalysis:
        """Analyze what needs indexing when switching branches."""
        
        # Find merge base between branches
        merge_base = self._get_merge_base(old_branch, new_branch)
        
        # Get files that changed between branches
        changed_files = self._get_changed_files(old_branch, new_branch)
        
        # Get working directory changes
        staged_files = self._get_staged_files()
        unstaged_files = self._get_unstaged_files()
        
        # Get branch ancestry for Qdrant filtering
        branch_ancestry = self._get_branch_ancestry(new_branch)
        
        return BranchChangeAnalysis(
            files_to_reindex=changed_files,
            files_to_update_metadata=self._get_unchanged_files(changed_files),
            staged_files=staged_files,
            unstaged_files=unstaged_files,
            merge_base=merge_base,
            branch_ancestry=branch_ancestry
        )
    
    def _get_merge_base(self, branch1: str, branch2: str) -> Optional[str]:
        """Find common ancestor between branches."""
        result = subprocess.run([
            "git", "merge-base", branch1, branch2
        ], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    
    def _get_changed_files(self, old_branch: str, new_branch: str) -> List[str]:
        """Get files that changed between branches using efficient git diff."""
        result = subprocess.run([
            "git", "diff", "--name-only", f"{old_branch}..{new_branch}"
        ], capture_output=True, text=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    
    def _get_branch_ancestry(self, branch: str) -> List[str]:
        """Get all parent branches for Qdrant filtering."""
        # Use git log --first-parent to get linear ancestry
        result = subprocess.run([
            "git", "log", "--first-parent", "--format=%H", branch
        ], capture_output=True, text=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
```

### 2. Smart Incremental Branch Indexer

```python
class SmartBranchIndexer:
    """Handles branch-aware incremental indexing."""
    
    def handle_branch_change(self, analysis: BranchChangeAnalysis) -> IndexingStats:
        """Execute smart incremental indexing based on branch analysis."""
        
        stats = IndexingStats()
        
        # 1. Batch update metadata for unchanged files (fast operation)
        if analysis.files_to_update_metadata:
            self._batch_update_branch_metadata(
                analysis.files_to_update_metadata, 
                analysis.new_branch
            )
            stats.metadata_updates = len(analysis.files_to_update_metadata)
        
        # 2. Reindex only changed files between branches
        if analysis.files_to_reindex:
            changed_stats = self._reindex_files(analysis.files_to_reindex)
            stats.merge(changed_stats)
        
        # 3. Index staged files (uncommitted changes)
        if analysis.staged_files:
            staged_stats = self._index_working_directory_files(
                analysis.staged_files, 
                status="staged"
            )
            stats.merge(staged_stats)
        
        # 4. Index unstaged files (working directory changes)  
        if analysis.unstaged_files:
            unstaged_stats = self._index_working_directory_files(
                analysis.unstaged_files,
                status="unstaged"
            )
            stats.merge(unstaged_stats)
        
        return stats
    
    def _batch_update_branch_metadata(self, files: List[str], new_branch: str):
        """Efficiently update branch metadata without reprocessing content."""
        
        # Use Qdrant's update API for bulk metadata changes
        updates = []
        for file_path in files:
            # Find existing points for this file
            existing_points = self.qdrant_client.search_by_file(file_path)
            
            for point in existing_points:
                updates.append({
                    "id": point.id,
                    "payload": {
                        **point.payload,
                        "git_branch": new_branch,
                        "last_updated": time.time()
                    }
                })
        
        # Batch update in chunks
        batch_size = 100
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            self.qdrant_client.batch_update_points(batch)
```

### 3. Enhanced Qdrant Integration with Branch Topology

```python
class EnhancedQdrantClient(QdrantClient):
    """Extended Qdrant client with branch topology support."""
    
    def create_branch_topology_indexes(self):
        """Create optimized indexes for branch-aware filtering."""
        indexes = [
            ("git_branch", "keyword"),           # Current branch  
            ("git_commit_hash", "keyword"),      # Specific commit
            ("git_merge_base", "keyword"),       # Merge base for topology
            ("working_directory_status", "keyword"), # staged/unstaged/committed
            ("branch_ancestry", "keyword"),      # Parent branches
            ("file_change_type", "keyword"),     # added/modified/deleted
        ]
        
        for field, schema in indexes:
            self.create_payload_index(field, schema)
    
    def search_with_branch_topology(
        self, 
        query_vector: List[float],
        current_branch: str,
        include_ancestry: bool = True,
        include_working_dir: bool = True
    ) -> List[Dict]:
        """Search with intelligent branch topology filtering."""
        
        # Build branch-aware filter
        branch_filter = self._build_topology_filter(
            current_branch, include_ancestry, include_working_dir
        )
        
        return self.search_with_filter(query_vector, branch_filter)
    
    def _build_topology_filter(
        self, 
        current_branch: str, 
        include_ancestry: bool,
        include_working_dir: bool
    ) -> Dict:
        """Build optimized filter for branch topology search."""
        
        filters = []
        
        # Include current branch files
        filters.append({
            "key": "git_branch", 
            "match": {"value": current_branch}
        })
        
        # Include parent branch ancestry if requested
        if include_ancestry:
            ancestry = self.git_service.get_branch_ancestry(current_branch)
            if ancestry:
                filters.append({
                    "key": "branch_ancestry",
                    "match": {"any": ancestry}
                })
        
        # Include working directory changes if requested
        if include_working_dir:
            filters.append({
                "key": "working_directory_status",
                "match": {"any": ["staged", "unstaged"]}
            })
        
        return {"should": filters}
```

### 4. Performance Optimizations

```python
class PerformanceOptimizedGitOperations:
    """Batch git operations for better performance."""
    
    def batch_file_analysis(self, files: List[str]) -> Dict[str, FileAnalysis]:
        """Analyze multiple files in batched git operations."""
        
        # Batch git hash-object for all files
        hashes = self._batch_git_hash_object(files)
        
        # Batch git log for last modified info
        modifications = self._batch_git_log_analysis(files)
        
        # Batch file status checks
        statuses = self._batch_git_status_analysis(files)
        
        # Combine results
        analysis = {}
        for file_path in files:
            analysis[file_path] = FileAnalysis(
                content_hash=hashes.get(file_path),
                last_modified=modifications.get(file_path),
                git_status=statuses.get(file_path)
            )
        
        return analysis
    
    def _batch_git_hash_object(self, files: List[str]) -> Dict[str, str]:
        """Batch git hash-object operation for performance."""
        
        # Use --stdin-paths for batch processing
        process = subprocess.run([
            "git", "hash-object", "--stdin-paths"
        ], input='\n'.join(files), capture_output=True, text=True)
        
        hashes = process.stdout.strip().split('\n')
        return dict(zip(files, hashes)) if hashes else {}
```

### 5. Implementation Plan

#### Phase 1: Core Infrastructure (Week 1-2)
1. **Implement GitTopologyService**
   - Branch relationship analysis
   - Merge base detection
   - File change analysis between branches
   
2. **Create Enhanced Qdrant Indexes**
   - Add branch topology payload indexes
   - Implement batch update operations
   - Add working directory status tracking

#### Phase 2: Smart Incremental Logic & Integration (Week 3-4) 
1. **Implement SmartBranchIndexer**
   - Branch change analysis
   - Incremental file processing
   - Working directory file handling
   
2. **Batch Git Operations**
   - Replace individual subprocess calls
   - Implement batch hash-object operations
   - Add parallel file processing

3. **Integration with SmartIndexer**
   - Replace current branch handling
   - Add resumable branch operations
   - Implement progress tracking

4. **Documentation Updates**
   - Update README with new branch topology features
   - Update CLI help text for new options
   - Add configuration documentation
   - Update examples and usage patterns

5. **Comprehensive Branch Topology E2E Test**
   - Create new test file: `test_branch_topology_e2e.py`
   - Test complete branch switching workflow with incremental indexing
   - Validate only changed files are reprocessed
   - Verify branch isolation and cleanup

### Branch Topology E2E Test Specification

```python
def test_complete_branch_topology_workflow(test_git_project):
    """
    Comprehensive E2E test for branch topology smart indexing.
    
    Test Steps:
    1. Initialize project and setup services
    2. Index master branch (baseline)
    3. Create new branch 'feature/test-branch'
    4. Add new file 'feature.py' in new branch
    5. Run indexing logic - verify only new file was processed
    6. Query for new file 'feature.py' - should be visible
    7. Query for existing master branch file - should also be visible (topology awareness)
    8. Switch back to master branch
    9. Remove test branch (git branch -D feature/test-branch)
    10. Query again for 'feature.py' - should return no results
    11. Cleanup: remove the added record for the test branch from Qdrant
    
    Validation Points:
    - Only changed files indexed on branch switch (incremental behavior)
    - Branch topology awareness (parent branch visibility from feature branch)
    - Proper cleanup of branch-specific data after branch deletion
    - Working directory file support (staged/unstaged)
    - Performance: O(δ) not O(n) indexing behavior
    - Complete environment cleanup after test
    """
```

**Key Test Scenarios:**
1. **Branch Creation & File Addition**
   - Create feature branch from master
   - Add unique file to feature branch
   - Verify incremental indexing (only new file processed)

2. **Branch Topology Search**
   - Query from feature branch should see:
     - New feature branch files
     - Parent branch (master) files via topology
   - Validate branch ancestry in search results

3. **Working Directory Support**
   - Test staged files indexing
   - Test unstaged files indexing
   - Verify working directory status metadata

4. **Branch Switching Performance**
   - Measure time for branch switch indexing
   - Verify O(δ) complexity (changed files only)
   - Compare with current O(n) implementation

5. **Cleanup & Isolation**
   - Branch deletion removes branch-specific vectors
   - Queries after branch deletion return no results
   - Master branch queries unaffected by cleanup

### 6. Expected Performance Improvements

**Current Performance (Branch Switch):**
- Time: O(n) where n = total files in branch
- Git operations: O(n) subprocess calls
- Qdrant operations: O(n) full reprocessing

**Optimized Performance (Branch Switch):**
- Time: O(δ) where δ = changed files between branches  
- Git operations: O(1) batch operations
- Qdrant operations: O(δ) incremental + O(n) metadata updates (fast)

**Expected Improvements:**
- **10-100x faster branch switches** for large repos with small deltas
- **90% reduction in git subprocess overhead** through batching
- **Intelligent working directory support** for staged/unstaged files
- **Branch topology-aware search** for better semantic context

### 7. Configuration Options

```python
# New configuration options for branch topology features
class BranchTopologyConfig:
    # Branch change detection
    enable_branch_topology: bool = True
    max_branch_ancestry_depth: int = 100
    
    # Working directory handling
    index_staged_files: bool = True
    index_unstaged_files: bool = True
    working_dir_update_interval: int = 300  # 5 minutes
    
    # Performance tuning
    batch_git_operations: bool = True
    max_git_batch_size: int = 1000
    branch_metadata_batch_size: int = 500
    
    # Search behavior
    default_include_ancestry: bool = True
    default_include_working_dir: bool = True
```

This comprehensive solution addresses all the key requirements:
- ✅ Smart incremental indexing on branch changes
- ✅ Branch topology awareness with merge base analysis
- ✅ Staged and unstaged file handling
- ✅ Performance optimization through batching and indexing
- ✅ Large codebase scalability
- ✅ Integration with existing Qdrant infrastructure

The solution provides dramatic performance improvements for large repositories while maintaining the robustness and git-aware features of the current implementation.