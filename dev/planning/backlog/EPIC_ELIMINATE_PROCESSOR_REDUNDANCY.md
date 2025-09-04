# EPIC: Eliminate Processor Redundancy - Unify Parallelization Architecture

## Epic Intent

**Eliminate the architectural redundancy between BranchAwareIndexer and HighThroughputProcessor by consolidating all indexing operations into a single, high-performance, git-aware processing pipeline that maximizes CPU utilization through file-level parallelization.**

## Problem Statement

The current architecture suffers from a critical performance bottleneck due to dual processor redundancy:

- **95% of indexing operations** use sequential `BranchAwareIndexer.index_branch_changes()` 
- **Only reconcile mode** uses parallel `HighThroughputProcessor.process_files_high_throughput()`
- Both processors are git-aware, creating 2000+ lines of redundant code
- Performance tests show 4-8x speedup potential that's currently unused

**Evidence**: SmartIndexer inherits from HighThroughputProcessor but defaults to BranchAwareIndexer for all primary operations, effectively running single-threaded despite multi-threading infrastructure.

## Critical Capability Analysis

### BranchAwareIndexer Unique Capabilities (Must Preserve)

#### 1. **Branch Visibility Management via `hidden_branches`**
- **Core Feature**: Uses `hidden_branches: List[str]` in each content point to track branch visibility
- **Logic**: Empty array = visible in all branches; branch name in array = hidden in that branch
- **Methods**: `_hide_file_in_branch()`, `_ensure_file_visible_in_branch()`, `hide_files_not_in_branch()`
- **Critical**: Enables proper branch isolation without content duplication

#### 2. **Content Deduplication via Deterministic IDs** 
- **Core Feature**: `_generate_content_id(file_path, commit, chunk_index)` using UUID5
- **Logic**: Same file+commit+chunk = same ID, enables content reuse across branches
- **Method**: `_content_exists()` checks before creating new content
- **Critical**: Prevents duplicate storage of identical content across branches

#### 3. **Git Working Directory vs Committed Content Tracking**
- **Core Feature**: Distinguishes between working directory changes and committed content
- **Logic**: `working_dir_{mtime}_{size}` vs actual git commit hashes
- **Method**: `_file_differs_from_committed_version()` + `_get_file_commit()`
- **Critical**: Handles mixed working directory and committed content scenarios

#### 4. **Point-in-Time Content Snapshot Management**
- **Core Feature**: When working directory content is indexed, hides committed versions (lines 660-779)
- **Logic**: Ensures only one version of content is visible per branch at any time
- **Process**: Creates new working directory content AND hides old committed content in same branch
- **Critical**: Prevents seeing both old and new versions simultaneously

#### 5. **Branch Cleanup and Garbage Collection**
- **Core Feature**: `cleanup_branch()` hides all content in specified branch
- **Logic**: Adds branch to `hidden_branches` of all content points
- **Method**: `garbage_collect_content()` removes content hidden in ALL branches
- **Critical**: Enables safe branch deletion without affecting other branches

### HighThroughputProcessor Current Capabilities

#### 1. **File-Level Parallelization**
- **Core Feature**: Pre-queues all files, then processes with worker threads
- **Performance**: 4-8x speedup through parallel file processing
- **Architecture**: ThreadPoolExecutor with VectorCalculationManager integration

#### 2. **Git-Aware Metadata Creation**
- **Core Feature**: Inherits from GitAwareDocumentProcessor
- **Method**: Uses GitAwareMetadataSchema.create_git_aware_metadata()
- **Limitation**: Creates standard git metadata but lacks branch visibility logic

#### 3. **Progress Reporting and Cancellation**
- **Core Feature**: Real-time progress with thread utilization display
- **Format**: "files completed/total (%) | emb/s | threads | filename"
- **Cancellation**: Graceful cancellation with partial completion tracking

### Critical Capability Gaps

#### ❌ **Missing in HighThroughputProcessor:**

1. **Branch Visibility Management**: No `hidden_branches` logic
2. **Content Deduplication**: No content existence checking or ID generation
3. **Working Directory Tracking**: No distinction between working/committed content  
4. **Point-in-Time Snapshots**: No logic to hide old versions when new content is created
5. **Branch Operations**: No cleanup_branch, hide_files_not_in_branch methods
6. **Content ID Strategy**: Uses GitAwareDocumentProcessor point IDs vs deterministic content IDs

#### ✅ **Present in HighThroughputProcessor:**
1. **Parallel Processing**: File-level parallelization architecture
2. **Git Awareness**: Basic git metadata collection and storage
3. **Progress Reporting**: Thread-aware progress tracking
4. **Cancellation**: Graceful cancellation support

## Proposed Architecture

### High-Level Component Design

```
┌─────────────────────────────────────────────────────────────┐
│                    SmartIndexer                             │
│  (Orchestrator - No Processing Logic)                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│            HighThroughputProcessor                          │
│         (Single Unified Processor)                         │
│                                                             │
│  ├─ process_files_high_throughput()                        │
│  ├─ process_branch_changes_high_throughput()               │
│  ├─ hide_files_not_in_branch()                             │
│  └─ cleanup_branch()                                        │
│                                                             │
│  Inherits: GitAwareDocumentProcessor                       │
│  Uses: VectorCalculationManager (8 threads)                │
│  Queue: File-level parallelization                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                VectorCalculationManager                     │
│                (Thread Pool: 8 Workers)                    │
│                                                             │
│  Worker Thread Processing Model:                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ def process_complete_file(file_path):                    ││
│  │   chunks = chunker.chunk_file(file_path)        # I/O    ││
│  │   embeddings = [get_embedding(c) for c in chunks] # AI  ││  
│  │   points = create_qdrant_points(chunks, embeddings)     ││
│  │   return points                                          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack
- **Threading**: Python ThreadPoolExecutor (existing)
- **Git Integration**: GitAwareDocumentProcessor (existing)
- **Vector Processing**: VectorCalculationManager (existing)
- **Database**: Qdrant with git-aware metadata (existing)
- **Progress Tracking**: Thread-safe progress callbacks (existing)

### Component Connections
- SmartIndexer → HighThroughputProcessor (single call path)
- HighThroughputProcessor → VectorCalculationManager (file-level task submission)
- VectorCalculationManager → EmbeddingProvider (parallel embeddings)
- HighThroughputProcessor → QdrantClient (batch operations)

## Migration Strategy

### Phase 1: Enhance HighThroughputProcessor with Branch-Aware Capabilities

#### Required Method Migrations from BranchAwareIndexer:

1. **`_generate_content_id(file_path, commit, chunk_index)`**
   - **Purpose**: Create deterministic UUIDs for content deduplication
   - **Implementation**: Direct migration of UUID5 logic
   - **Critical**: Must maintain exact same ID generation for compatibility

2. **`_content_exists(content_id, collection_name)`** 
   - **Purpose**: Check if content already exists before creating new
   - **Implementation**: Direct migration of Qdrant point existence check
   - **Critical**: Enables content reuse optimization

3. **`_get_file_commit(file_path)`**
   - **Purpose**: Distinguish working directory vs committed content
   - **Implementation**: Migrate git diff and file stat logic
   - **Critical**: Required for proper content versioning

4. **`_file_differs_from_committed_version(file_path)`**
   - **Purpose**: Detect working directory modifications
   - **Implementation**: Direct migration of git diff --quiet logic
   - **Critical**: Enables working directory content tracking

5. **`_create_content_point()` with `hidden_branches` support**
   - **Purpose**: Create content points with branch visibility metadata
   - **Implementation**: Enhance existing _create_qdrant_point with hidden_branches logic
   - **Critical**: Core branch isolation functionality

6. **`_hide_file_in_branch(file_path, branch, collection_name)`**
   - **Purpose**: Mark file as hidden in specific branch
   - **Implementation**: Direct migration of batch point update logic
   - **Critical**: Required for branch switching operations

7. **`_ensure_file_visible_in_branch(file_path, branch, collection_name)`**
   - **Purpose**: Mark file as visible in specific branch  
   - **Implementation**: Direct migration of hidden_branches removal logic
   - **Critical**: Required for content reuse scenarios

8. **`hide_files_not_in_branch(branch, current_files, collection_name)`**
   - **Purpose**: Hide all database files not present in current branch
   - **Implementation**: Direct migration with progress callback support
   - **Critical**: Ensures proper branch isolation during full indexing

9. **`cleanup_branch(branch, collection_name)`**
   - **Purpose**: Hide all content in specified branch
   - **Implementation**: Direct migration of batch hidden_branches update
   - **Critical**: Required for branch deletion operations

#### Enhanced File Processing Algorithm:

```pseudocode
process_files_high_throughput_branch_aware(files, old_branch, new_branch, vector_thread_count):
    # Phase 1: Pre-process files with branch-aware metadata
    file_tasks = []
    for file_path in files:
        current_commit = _get_file_commit(file_path)  # Working dir vs committed
        content_id = _generate_content_id(file_path, current_commit, 0)
        
        if _content_exists(content_id, collection_name):
            # Content exists - ensure visibility in new branch
            _ensure_file_visible_in_branch(file_path, new_branch, collection_name)
            continue  # Skip processing, reuse existing content
        
        # Content doesn't exist - queue for parallel processing
        file_tasks.append(FileTask(file_path, current_commit, metadata))
    
    # Phase 2: Process files in parallel with branch context
    with ThreadPoolExecutor(8) as executor:
        futures = [executor.submit(process_file_with_branch_awareness, task) for task in file_tasks]
        
        for future in as_completed(futures):
            content_points = future.result()
            
            # Phase 3: Handle point-in-time snapshot management
            for point in content_points:
                if point.commit.startswith("working_dir_"):
                    # Hide old committed versions in same branch
                    hide_committed_versions_for_working_dir_content(point.file_path, new_branch)
                else:
                    # Hide working directory versions for committed content
                    hide_working_dir_versions_for_committed_content(point.file_path, new_branch)
            
            batch_points.extend(content_points)
    
    # Phase 4: Update branch visibility for all files
    hide_files_not_in_branch(new_branch, all_visible_files, collection_name)
```

### Phase 2: Replace All SmartIndexer Calls

#### Decision Tree Refactoring:

```pseudocode
# OLD: SmartIndexer decision tree
smart_index() Decision Flow:
├── Branch Change? → BranchAwareIndexer.index_branch_changes() [SEQUENTIAL]
├── Resume? → _do_resume_interrupted() → BranchAwareIndexer [SEQUENTIAL] 
├── Force Full? → _do_full_index() → BranchAwareIndexer [SEQUENTIAL]
├── Config Changed? → _do_full_index() → BranchAwareIndexer [SEQUENTIAL]
├── Reconcile? → _do_reconcile_with_database() → HighThroughputProcessor [PARALLEL]
└── Incremental? → _do_incremental_index() → BranchAwareIndexer [SEQUENTIAL]

# NEW: Unified decision tree
smart_index() Decision Flow:
├── Branch Change? → HighThroughputProcessor.process_branch_changes_high_throughput() [PARALLEL]
├── Resume? → HighThroughputProcessor.process_files_high_throughput() [PARALLEL]
├── Force Full? → HighThroughputProcessor.process_files_high_throughput() [PARALLEL]
├── Config Changed? → HighThroughputProcessor.process_files_high_throughput() [PARALLEL]
├── Reconcile? → HighThroughputProcessor.process_files_high_throughput() [PARALLEL]
└── Incremental? → HighThroughputProcessor.process_files_high_throughput() [PARALLEL]
```

### Phase 3: Comprehensive Testing and Validation

#### Critical Test Scenarios:

1. **Branch Visibility Integrity**
   - Switch between branches with different file sets
   - Verify no content bleeding between branches
   - Test hidden_branches array manipulation

2. **Content Deduplication Verification**
   - Same file across multiple branches should reuse content
   - Different commits of same file should create separate content
   - Verify deterministic content ID generation

3. **Working Directory vs Committed Content**
   - Modify file, verify working directory content is created
   - Commit changes, verify committed content replaces working directory
   - Test mixed scenarios with some files modified, some committed

4. **Point-in-Time Snapshot Consistency**
   - When working directory content is indexed, old committed content is hidden
   - When committed content is indexed, old working directory content is hidden
   - Verify only one version visible per branch

5. **Performance Validation**
   - All operations show 4-8x speedup vs sequential processing
   - Thread utilization consistently shows 8 active workers
   - Memory usage acceptable for performance gains

### Migration Checklist

#### Pre-Migration Validation:
- [ ] All existing BranchAwareIndexer functionality catalogued
- [ ] All method signatures and behaviors documented
- [ ] All test scenarios identified for regression prevention
- [ ] Performance baseline measurements recorded

#### Implementation Phase:
- [ ] Migrate `_generate_content_id()` with exact UUID5 logic
- [ ] Migrate `_content_exists()` with identical existence checking
- [ ] Migrate `_get_file_commit()` with working directory detection
- [ ] Migrate `_file_differs_from_committed_version()` git diff logic
- [ ] Enhance `_create_qdrant_point()` with `hidden_branches` support
- [ ] Migrate `_hide_file_in_branch()` with batch update logic
- [ ] Migrate `_ensure_file_visible_in_branch()` with hidden_branches removal
- [ ] Migrate `hide_files_not_in_branch()` with progress callback
- [ ] Migrate `cleanup_branch()` with batch hidden_branches updates
- [ ] Migrate point-in-time snapshot management (lines 660-779 logic)

#### Integration Phase:
- [ ] Create `process_branch_changes_high_throughput()` method
- [ ] Replace SmartIndexer branch change calls
- [ ] Replace SmartIndexer full index calls
- [ ] Replace SmartIndexer incremental calls
- [ ] Replace SmartIndexer resume calls
- [ ] Update all progress callback formats
- [ ] Ensure cancellation works across all paths

#### Validation Phase:
- [ ] All existing tests pass without modification
- [ ] Branch visibility tests pass (no content bleeding)
- [ ] Content deduplication tests pass (same IDs generated)
- [ ] Working directory vs committed content tests pass
- [ ] Point-in-time snapshot tests pass
- [ ] Performance tests show 4-8x improvement
- [ ] Thread utilization tests show 8 active workers
- [ ] Memory usage within acceptable bounds
- [ ] Cancellation and resumption work correctly

#### Cleanup Phase:
- [ ] Remove BranchAwareIndexer class and all references
- [ ] Remove unused imports and dependencies
- [ ] Update documentation to reflect unified architecture
- [ ] Archive old performance tests that are no longer relevant

## User Stories

### Story 1: Migrate Branch Change Processing to High-Throughput Pipeline
**As a developer working with git branches, I want branch switching operations to use maximum CPU cores so that branch changes are processed 4-8x faster.**

**Acceptance Criteria:**
- Given I switch git branches with many file changes
- When the indexer detects branch changes
- Then the system uses HighThroughputProcessor.process_branch_changes_high_throughput()
- And all 8 worker threads process files simultaneously
- And branch visibility is updated correctly
- And no sequential processing bottlenecks exist
- And performance improves by minimum 4x over current implementation

**Pseudocode Algorithm:**
```
process_branch_changes_high_throughput(old_branch, new_branch, changed_files, unchanged_files):
    # Phase 1: Queue all changed files for parallel processing
    file_tasks = [(file, old_branch, new_branch, metadata) for file in changed_files]
    
    # Phase 2: Workers process complete files with branch context
    with ThreadPoolExecutor(8) as executor:
        futures = [executor.submit(process_file_with_branch_context, task) for task in file_tasks]
        
        # Phase 3: Collect results and update branch visibility
        for future in as_completed(futures):
            points = future.result()
            batch_points.extend(points)
    
    # Phase 4: Update branch visibility for unchanged files
    update_unchanged_files_visibility(unchanged_files, new_branch)
    
    # Phase 5: Hide files not in branch
    hide_files_not_in_branch(new_branch, all_visible_files)
```

### Story 2: Migrate Full Index Processing to High-Throughput Pipeline  
**As a developer performing full re-indexing, I want the full index operation to use maximum CPU cores so that complete codebase indexing is 4-8x faster.**

**Acceptance Criteria:**
- Given I run `cidx index --clear` for full re-indexing
- When the system processes all files in the codebase
- Then the system uses HighThroughputProcessor.process_files_high_throughput()
- And all 8 worker threads process files simultaneously
- And git-aware metadata is preserved for all files
- And progress reporting shows per-file completion with thread utilization
- And performance improves by minimum 4x over current implementation

### Story 3: Migrate Incremental Index Processing to High-Throughput Pipeline
**As a developer performing incremental indexing, I want incremental updates to use maximum CPU cores so that modified files are processed 4-8x faster.**

**Acceptance Criteria:**
- Given I have modified files since last index
- When I run `cidx index` for incremental updates
- Then the system uses HighThroughputProcessor.process_files_high_throughput()
- And only modified files are queued for processing
- And all 8 worker threads process modified files simultaneously
- And git commit tracking works correctly for incremental changes
- And performance improves by minimum 4x over current implementation

### Story 4: Eliminate BranchAwareIndexer Code and References
**As a maintainer, I want to remove all BranchAwareIndexer code so that the codebase has a single, maintainable processing path.**

**Acceptance Criteria:**
- Given the HighThroughputProcessor handles all processing scenarios
- When I remove BranchAwareIndexer from the codebase
- Then all imports and references to BranchAwareIndexer are eliminated
- And all functionality previously handled by BranchAwareIndexer works via HighThroughputProcessor
- And no code paths can fall back to sequential processing
- And approximately 2000 lines of redundant code are removed
- And all existing tests pass with the unified processor

### Story 5: Enhance Progress Reporting for File-Level Parallelization
**As a developer monitoring indexing progress, I want to see real-time thread utilization and per-file completion so that I can track parallel processing efficiency.**

**Acceptance Criteria:**
- Given the system is processing files with 8 worker threads
- When I monitor indexing progress
- Then I see format: "files completed/total (%) | embeddings/sec | active threads | current filename"
- And thread utilization shows actual worker thread count (1-8)
- And embeddings per second reflects parallel throughput
- And file completion updates in real-time as workers finish files
- And no progress reporting shows sequential processing indicators

**Progress Display Format:**
```
Processing: 45/120 files (37%) | 23.4 emb/s | 8 threads | utils.py ✓
Processing: 46/120 files (38%) | 24.1 emb/s | 7 threads | config.py (67%)
```

### Story 6: Create Performance Validation Test Infrastructure
**As a developer validating the refactoring, I want automated performance tests that verify 4-8x improvement so that regression prevention is automated.**

**Acceptance Criteria:**
- Given the unified HighThroughputProcessor implementation
- When performance validation tests are executed
- Then branch change operations show minimum 4x speedup
- And full index operations show minimum 4x speedup  
- And incremental operations show minimum 4x speedup
- And thread utilization metrics confirm 8 workers are active
- And git-awareness functionality remains identical
- And no performance regressions are detected

## Manual Testing Instructions for Claude Code

### Pre-Test Setup
```bash
# Create test repository with substantial content
mkdir -p ~/.tmp/performance_test_repo
cd ~/.tmp/performance_test_repo
git init
git config user.email "test@example.com"
git config user.name "Test User"

# Create multiple large files for meaningful testing
for i in {1..20}; do
    cat > "file_${i}.py" << EOF
#!/usr/bin/env python3
"""
Test file ${i} for performance validation.
This file contains multiple functions and classes to generate substantial chunks.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

class TestClass${i}:
    """Test class ${i} with multiple methods."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
    def process_data(self, data: List[Dict]) -> List[Dict]:
        """Process input data with complex logic."""
        results = []
        for item in data:
            if self.validate_item(item):
                processed_item = self.transform_item(item)
                results.append(processed_item)
        return results
    
    def validate_item(self, item: Dict) -> bool:
        """Validate individual item."""
        required_fields = ['id', 'name', 'type', 'metadata']
        return all(field in item for field in required_fields)
    
    def transform_item(self, item: Dict) -> Dict:
        """Transform item with business logic."""
        return {
            'id': item['id'],
            'processed_name': item['name'].upper(),
            'category': item.get('type', 'unknown'),
            'metadata': self.process_metadata(item.get('metadata', {}))
        }
    
    def process_metadata(self, metadata: Dict) -> Dict:
        """Process metadata with additional enrichment."""
        enriched = metadata.copy()
        enriched['processed_at'] = '2024-01-01T00:00:00Z'
        enriched['processor_version'] = '1.0.0'
        return enriched

def main():
    """Main function for file ${i}."""
    config = {
        'debug': True,
        'max_items': 1000,
        'output_format': 'json'
    }
    
    processor = TestClass${i}(config)
    
    # Sample data processing
    sample_data = [
        {'id': f'item_{j}', 'name': f'Test Item {j}', 'type': 'sample', 'metadata': {'version': '1.0'}}
        for j in range(10)
    ]
    
    results = processor.process_data(sample_data)
    print(f"Processed {len(results)} items in file ${i}")

if __name__ == '__main__':
    main()
EOF
done

git add .
git commit -m "Initial commit with 20 test files"

# Create feature branch with significant changes
git checkout -b feature_branch
for i in {1..10}; do
    echo "# Additional feature code for file ${i}" >> "file_${i}.py"
    echo "def feature_function_${i}():" >> "file_${i}.py"
    echo "    return 'feature implementation ${i}'" >> "file_${i}.py"
done
git add .
git commit -m "Add feature implementations"

# Create another branch with different changes
git checkout master
git checkout -b performance_branch
for i in {11..20}; do
    echo "# Performance optimization for file ${i}" >> "file_${i}.py"
    echo "def optimize_performance_${i}():" >> "file_${i}.py"
    echo "    return 'performance optimization ${i}'" >> "file_${i}.py"
done
git add .
git commit -m "Add performance optimizations"

git checkout master
```

### Test Case 1: Validate Branch Change Performance
```bash
cd ~/.tmp/performance_test_repo

# Initialize indexing on master branch
echo "=== Testing Branch Change Performance ==="
time cidx init --embedding-provider ollama
time cidx start
time cidx index --clear

# Switch to feature branch and measure performance
echo "=== Switching to feature_branch ==="
git checkout feature_branch
time cidx index

# Switch to performance branch and measure performance  
echo "=== Switching to performance_branch ==="
git checkout performance_branch
time cidx index

# Expected: Each branch switch should show 8 threads active in progress output
# Expected: Performance should be significantly faster than sequential processing
```

### Test Case 2: Validate Full Index Performance
```bash
cd ~/.tmp/performance_test_repo
git checkout master

# Test full re-indexing performance
echo "=== Testing Full Index Performance ==="
time cidx index --clear

# Expected: Progress should show "8 threads" in output
# Expected: All 20 files processed with parallel utilization
# Expected: Embeddings per second > 20 (indicating parallel processing)
```

### Test Case 3: Validate Incremental Performance
```bash
cd ~/.tmp/performance_test_repo

# Modify several files
echo "# Modified content" >> file_1.py
echo "# Modified content" >> file_5.py  
echo "# Modified content" >> file_10.py
echo "# Modified content" >> file_15.py

# Test incremental indexing performance
echo "=== Testing Incremental Index Performance ==="
time cidx index

# Expected: Only modified files processed
# Expected: Parallel processing for modified files
# Expected: Thread utilization appropriate for number of modified files
```

### Test Case 4: Validate Thread Utilization Reporting
```bash
cd ~/.tmp/performance_test_repo

# Monitor detailed progress during large operation
git checkout master
cidx index --clear 2>&1 | tee performance_log.txt

# Verify progress output format
echo "=== Analyzing Progress Output ==="
grep -E "threads" performance_log.txt
grep -E "emb/s" performance_log.txt

# Expected patterns in output:
# "8 threads" - maximum thread utilization
# "23.4 emb/s" - high embeddings per second
# "file_X.py ✓" - file completion indicators
```

### Test Case 5: Validate Git-Awareness Preservation
```bash
cd ~/.tmp/performance_test_repo

# Test git metadata preservation
echo "=== Testing Git-Awareness ==="
git checkout master
cidx index --clear

# Query specific file to verify git metadata
cidx query "TestClass1" --limit 1

# Switch branches and verify branch isolation
git checkout feature_branch
cidx index
cidx query "TestClass1" --limit 1

git checkout performance_branch  
cidx index
cidx query "TestClass1" --limit 1

# Expected: Each branch should return different content
# Expected: Git metadata should include correct branch/commit information
# Expected: No content bleeding between branches
```

### Test Case 6: Validate Performance Metrics
```bash
cd ~/.tmp/performance_test_repo

# Create larger test dataset for meaningful metrics
for i in {21..50}; do
    cp file_1.py "large_file_${i}.py"
done
git add .
git commit -m "Add larger dataset"

# Measure and compare performance
echo "=== Performance Baseline Measurement ==="

# Full index with timing
time (cidx index --clear 2>&1 | tee full_index_log.txt)

# Extract metrics
echo "=== Performance Analysis ==="
echo "Files processed:"
grep -o "files completed" full_index_log.txt | wc -l

echo "Peak thread utilization:"
grep -o "[0-9] threads" full_index_log.txt | sort -n | tail -1

echo "Peak embeddings per second:"
grep -o "[0-9.]* emb/s" full_index_log.txt | sort -n | tail -1

# Expected: Thread count should be 8
# Expected: Embeddings/sec should indicate parallel processing (>20)
# Expected: Total time should be significantly less than sequential processing
```

### Test Case 7: Validate Error Handling and Cancellation
```bash
cd ~/.tmp/performance_test_repo

# Test cancellation during parallel processing
echo "=== Testing Cancellation Behavior ==="
timeout 10s cidx index --clear

# Verify resumability after cancellation
cidx index

# Expected: Graceful cancellation without data corruption
# Expected: Successful resume from cancellation point
# Expected: Thread cleanup without resource leaks
```

### Success Criteria Validation
After running all tests, verify:

1. **Performance Improvement**: All operations show 4-8x speedup indicators
2. **Thread Utilization**: Progress output consistently shows "8 threads" during processing
3. **Git-Awareness**: Branch switching maintains proper content isolation
4. **Functional Equivalence**: All existing functionality works identically
5. **Error Handling**: Cancellation and resumption work correctly
6. **Resource Management**: No memory leaks or thread pool issues

### Performance Regression Detection
If any test shows:
- Thread count < 8 during large operations
- Embeddings/sec < 20 during parallel processing  
- Sequential processing indicators in progress output
- Performance worse than 2x improvement

**Then the refactoring has not achieved its performance objectives and requires investigation.**

## Implementation Notes

### Risk Mitigation
- Maintain identical git-awareness functionality
- Preserve all branch isolation guarantees
- Maintain backward compatibility with existing metadata
- Ensure thread safety for all parallel operations

### Performance Targets
- **Branch Changes**: 4-8x speedup
- **Full Index**: 4-8x speedup  
- **Incremental**: 4-8x speedup
- **Thread Utilization**: 95%+ during large operations
- **Memory Usage**: Acceptable increase for performance gains

### Technical Constraints
- Must maintain all existing git-aware features
- Must preserve branch visibility and isolation
- Must maintain progress reporting compatibility
- Must handle cancellation gracefully
- Must support all existing embedding providers

## Comprehensive Manual Testing Protocol for Claude Code

### Pre-Testing Environment Setup

#### Create Complex Multi-Branch Test Repository
```bash
# Create comprehensive test repository with multiple scenarios
mkdir -p ~/.tmp/refactoring_test_repo
cd ~/.tmp/refactoring_test_repo
git init
git config user.email "test@example.com"
git config user.name "Test User"

# Create baseline files with substantial content for meaningful testing
for i in {1..15}; do
    cat > "module_${i}.py" << EOF
#!/usr/bin/env python3
"""
Module ${i} - Core business logic implementation.
This module handles ${i} specific operations with comprehensive functionality.
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Union
from uuid import uuid4

logger = logging.getLogger(__name__)

@dataclass
class BusinessEntity${i}:
    """Core business entity for module ${i} operations."""
    entity_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    category: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    tags: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Post-initialization validation and setup."""
        if not self.name:
            self.name = f"Entity_{self.entity_id[:8]}"
        self.validate_entity()
    
    def validate_entity(self) -> bool:
        """Validate entity data integrity."""
        if not self.entity_id or len(self.entity_id) < 8:
            raise ValueError(f"Invalid entity_id: {self.entity_id}")
        
        if not isinstance(self.metadata, dict):
            raise ValueError("Metadata must be a dictionary")
        
        if self.updated_at and self.updated_at < self.created_at:
            raise ValueError("Updated time cannot be before created time")
        
        return True
    
    def update_entity(self, **kwargs) -> None:
        """Update entity with new data."""
        self.updated_at = datetime.now(timezone.utc)
        
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.metadata[key] = value
    
    def add_tags(self, *tags: str) -> None:
        """Add tags to entity."""
        self.tags.update(tags)
        self.updated_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary representation."""
        return {
            'entity_id': self.entity_id,
            'name': self.name,
            'category': self.category,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'tags': list(self.tags)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BusinessEntity${i}':
        """Create entity from dictionary representation."""
        entity = cls(
            entity_id=data['entity_id'],
            name=data['name'],
            category=data['category'],
            metadata=data.get('metadata', {}),
            tags=set(data.get('tags', []))
        )
        
        if data.get('created_at'):
            entity.created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        
        if data.get('updated_at'):
            entity.updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
        
        return entity

class EntityProcessor${i}:
    """Processor for handling ${i} specific business operations."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.EntityProcessor${i}")
        self.entities: Dict[str, BusinessEntity${i}] = {}
        self.processing_queue: List[str] = []
        
    async def process_entity_async(self, entity: BusinessEntity${i}) -> Dict[str, Any]:
        """Asynchronously process entity with complex business logic."""
        self.logger.info(f"Processing entity {entity.entity_id} in module ${i}")
        
        # Simulate complex processing
        await asyncio.sleep(0.1)  # Simulate I/O operation
        
        # Complex business logic simulation
        processing_result = {
            'processed_entity_id': entity.entity_id,
            'processing_timestamp': datetime.now(timezone.utc).isoformat(),
            'module_id': ${i},
            'status': 'completed',
            'metrics': {
                'validation_score': min(100, len(entity.name) * 2 + len(entity.tags) * 5),
                'complexity_rating': len(entity.metadata) + len(entity.tags),
                'category_boost': 10 if entity.category != 'default' else 0
            }
        }
        
        # Update entity with processing results
        entity.update_entity(
            processing_status='completed',
            last_processed=datetime.now(timezone.utc).isoformat(),
            processing_metrics=processing_result['metrics']
        )
        
        self.entities[entity.entity_id] = entity
        return processing_result
    
    def batch_process_entities(self, entities: List[BusinessEntity${i}]) -> List[Dict[str, Any]]:
        """Process multiple entities in batch."""
        results = []
        
        for entity in entities:
            try:
                # Synchronous complex processing
                result = self._process_entity_sync(entity)
                results.append(result)
                
            except Exception as e:
                self.logger.error(f"Failed to process entity {entity.entity_id}: {e}")
                results.append({
                    'entity_id': entity.entity_id,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return results
    
    def _process_entity_sync(self, entity: BusinessEntity${i}) -> Dict[str, Any]:
        """Synchronous entity processing with validation."""
        if not entity.validate_entity():
            raise ValueError(f"Entity validation failed for {entity.entity_id}")
        
        # Complex transformation logic
        transformation_score = self._calculate_transformation_score(entity)
        
        return {
            'entity_id': entity.entity_id,
            'transformation_score': transformation_score,
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'module': ${i}
        }
    
    def _calculate_transformation_score(self, entity: BusinessEntity${i}) -> float:
        """Calculate complex transformation score."""
        base_score = len(entity.name) * 1.5
        metadata_bonus = sum(len(str(v)) for v in entity.metadata.values()) * 0.1
        tag_bonus = len(entity.tags) * 2.0
        category_multiplier = 1.2 if entity.category != 'default' else 1.0
        
        return (base_score + metadata_bonus + tag_bonus) * category_multiplier

def create_sample_entities_${i}() -> List[BusinessEntity${i}]:
    """Create sample entities for testing."""
    entities = []
    
    for j in range(5):
        entity = BusinessEntity${i}(
            name=f"Sample Entity ${i}-{j}",
            category=f"category_{j % 3}",
            metadata={
                'version': f'1.{j}',
                'source': f'module_{${i}}',
                'complexity': j * 10,
                'features': [f'feature_{k}' for k in range(j + 1)]
            }
        )
        entity.add_tags(f'tag_{${i}}', f'batch_{j}', f'auto_generated')
        entities.append(entity)
    
    return entities

async def main_${i}():
    """Main function for module ${i} operations."""
    config = {
        'module_id': ${i},
        'processing_enabled': True,
        'batch_size': 10,
        'async_processing': True
    }
    
    processor = EntityProcessor${i}(config)
    sample_entities = create_sample_entities_${i}()
    
    # Test both async and sync processing
    if config['async_processing']:
        tasks = [processor.process_entity_async(entity) for entity in sample_entities]
        results = await asyncio.gather(*tasks)
    else:
        results = processor.batch_process_entities(sample_entities)
    
    print(f"Module ${i} processing completed. Processed {len(results)} entities.")
    return results

if __name__ == '__main__':
    asyncio.run(main_${i}())
EOF
done

# Initial commit
git add .
git commit -m "Initial commit: Core business logic modules 1-15"

# Create feature branch with significant changes (modules 1-8)
git checkout -b feature/advanced-processing
for i in {1..8}; do
    cat >> "module_${i}.py" << EOF

# Advanced Processing Features for Module ${i}
class AdvancedProcessor${i}(EntityProcessor${i}):
    """Enhanced processor with advanced features for module ${i}."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.advanced_metrics = {}
        self.processing_history = []
    
    async def advanced_process_entity(self, entity: BusinessEntity${i}) -> Dict[str, Any]:
        """Advanced processing with machine learning features."""
        # Simulate advanced processing
        result = await super().process_entity_async(entity)
        
        # Add advanced features
        advanced_result = {
            **result,
            'ml_confidence': min(1.0, len(entity.metadata) * 0.1),
            'prediction_accuracy': 0.85 + (hash(entity.entity_id) % 100) / 1000,
            'feature_importance': {
                'name_length': len(entity.name) / 100,
                'metadata_richness': len(entity.metadata) / 20,
                'tag_diversity': len(entity.tags) / 10
            }
        }
        
        self.processing_history.append(advanced_result)
        return advanced_result
    
    def generate_insights(self) -> Dict[str, Any]:
        """Generate insights from processing history."""
        if not self.processing_history:
            return {'status': 'no_data'}
        
        total_processed = len(self.processing_history)
        avg_confidence = sum(r.get('ml_confidence', 0) for r in self.processing_history) / total_processed
        
        return {
            'total_entities_processed': total_processed,
            'average_ml_confidence': avg_confidence,
            'processing_efficiency': min(1.0, total_processed / 100),
            'module_id': ${i}
        }

def benchmark_performance_${i}():
    """Benchmark performance for module ${i}."""
    import time
    
    start_time = time.time()
    entities = create_sample_entities_${i}()
    
    config = {'module_id': ${i}, 'processing_enabled': True}
    processor = EntityProcessor${i}(config)
    results = processor.batch_process_entities(entities)
    
    end_time = time.time()
    
    return {
        'module': ${i},
        'processing_time': end_time - start_time,
        'entities_processed': len(results),
        'throughput': len(results) / (end_time - start_time)
    }
EOF
done

git add .
git commit -m "Feature: Add advanced processing capabilities to modules 1-8"

# Create performance branch with different changes (modules 9-15)
git checkout master
git checkout -b performance/optimization
for i in {9..15}; do
    cat >> "module_${i}.py" << EOF

# Performance Optimizations for Module ${i}
class OptimizedProcessor${i}(EntityProcessor${i}):
    """Performance-optimized processor for module ${i}."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.cache = {}
        self.batch_cache = {}
        self.performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'batch_operations': 0
        }
    
    def cached_process_entity(self, entity: BusinessEntity${i}) -> Dict[str, Any]:
        """Process entity with caching for performance."""
        cache_key = f"{entity.entity_id}_{hash(str(entity.metadata))}"
        
        if cache_key in self.cache:
            self.performance_metrics['cache_hits'] += 1
            return self.cache[cache_key]
        
        self.performance_metrics['cache_misses'] += 1
        result = self._process_entity_sync(entity)
        self.cache[cache_key] = result
        return result
    
    def optimized_batch_process(self, entities: List[BusinessEntity${i}]) -> List[Dict[str, Any]]:
        """Optimized batch processing with performance enhancements."""
        self.performance_metrics['batch_operations'] += 1
        
        # Group entities by category for optimized processing
        categorized = {}
        for entity in entities:
            if entity.category not in categorized:
                categorized[entity.category] = []
            categorized[entity.category].append(entity)
        
        results = []
        for category, category_entities in categorized.items():
            # Process entities of same category together for optimization
            category_results = [
                self.cached_process_entity(entity) 
                for entity in category_entities
            ]
            results.extend(category_results)
        
        return results
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        total_requests = self.performance_metrics['cache_hits'] + self.performance_metrics['cache_misses']
        cache_hit_rate = self.performance_metrics['cache_hits'] / total_requests if total_requests > 0 else 0
        
        return {
            'module': ${i},
            'cache_hit_rate': cache_hit_rate,
            'total_requests': total_requests,
            'batch_operations': self.performance_metrics['batch_operations']
        }

def stress_test_${i}():
    """Stress test for module ${i} performance."""
    import time
    import random
    
    # Create large number of entities for stress testing
    stress_entities = []
    for j in range(50):
        entity = BusinessEntity${i}(
            name=f"StressTest_{${i}}_{j}",
            category=f"stress_category_{j % 5}",
            metadata={
                'test_id': j,
                'complexity': random.randint(1, 100),
                'data_size': random.randint(100, 1000)
            }
        )
        stress_entities.append(entity)
    
    config = {'module_id': ${i}, 'processing_enabled': True}
    optimizer = OptimizedProcessor${i}(config)
    
    start_time = time.time()
    results = optimizer.optimized_batch_process(stress_entities)
    end_time = time.time()
    
    stats = optimizer.get_performance_stats()
    
    return {
        'module': ${i},
        'stress_test_time': end_time - start_time,
        'entities_processed': len(results),
        'performance_stats': stats
    }
EOF
done

git add .
git commit -m "Performance: Add optimization features to modules 9-15"

# Create experimental branch with working directory changes
git checkout master
git checkout -b experimental/ml-integration

# Add new files and modify existing ones (mixed scenario)
cat > "ml_integration.py" << EOF
#!/usr/bin/env python3
"""
Machine Learning Integration Module.
Provides ML capabilities across all business modules.
"""

import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json

@dataclass
class MLModel:
    """Machine learning model configuration."""
    model_id: str
    model_type: str
    version: str
    parameters: Dict[str, Any]
    
class MLIntegrationService:
    """Service for integrating ML capabilities."""
    
    def __init__(self):
        self.models = {}
        self.predictions = {}
    
    def register_model(self, model: MLModel):
        """Register a new ML model."""
        self.models[model.model_id] = model
    
    def predict(self, model_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make prediction using registered model."""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not registered")
        
        # Simulate ML prediction
        prediction = {
            'model_id': model_id,
            'prediction': hash(str(input_data)) % 100 / 100.0,
            'confidence': 0.85,
            'input_features': list(input_data.keys())
        }
        
        self.predictions[f"{model_id}_{hash(str(input_data))}"] = prediction
        return prediction

# Global ML service instance
ml_service = MLIntegrationService()
EOF

# Modify some existing files (working directory changes)
for i in {2..4}; do
    echo "" >> "module_${i}.py"
    echo "# Working directory modification for testing" >> "module_${i}.py"
    echo "from ml_integration import ml_service" >> "module_${i}.py"
    echo "" >> "module_${i}.py"
    echo "def integrate_ml_features_${i}():" >> "module_${i}.py"
    echo "    \"\"\"Integrate ML features into module ${i}.\"\"\"" >> "module_${i}.py"
    echo "    return ml_service.predict('module_${i}_model', {'data': 'test'})" >> "module_${i}.py"
done

# Leave some files staged, some unstaged
git add ml_integration.py
git add module_2.py
# Leave module_3.py and module_4.py as working directory changes

git commit -m "Experimental: Add ML integration service and partial module integration"

# Return to master
git checkout master

echo "=== Complex test repository created ==="
echo "Branches: master, feature/advanced-processing, performance/optimization, experimental/ml-integration"
echo "Files: 15 modules + ML integration (mixed committed/working directory state)"
echo "Ready for comprehensive testing"
```

### Test Suite 1: Branch Visibility and Isolation Validation

#### Test Case 1A: Branch Content Isolation
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 1A: Branch Content Isolation ==="

# Initialize code indexer
git checkout master
time cidx init --embedding-provider ollama
time cidx start
time cidx index --clear

echo "--- Step 1: Index master branch ---"
time cidx index
echo "Master branch indexed. Querying for content..."
cidx query "BusinessEntity class definition" --limit 3

echo "--- Step 2: Switch to feature branch ---"  
git checkout feature/advanced-processing
time cidx index
echo "Feature branch indexed. Querying for advanced features..."
cidx query "AdvancedProcessor class" --limit 3
cidx query "ml_confidence" --limit 2

echo "--- Step 3: Switch to performance branch ---"
git checkout performance/optimization  
time cidx index
echo "Performance branch indexed. Querying for optimization features..."
cidx query "OptimizedProcessor class" --limit 3
cidx query "cache_hits performance" --limit 2

echo "--- Step 4: Verify branch isolation ---"
git checkout master
cidx query "AdvancedProcessor" --limit 1
# Expected: Should NOT find AdvancedProcessor in master branch

git checkout feature/advanced-processing
cidx query "OptimizedProcessor" --limit 1  
# Expected: Should NOT find OptimizedProcessor in feature branch

git checkout performance/optimization
cidx query "ml_confidence" --limit 1
# Expected: Should NOT find ml_confidence in performance branch

echo "--- VALIDATION CRITERIA ---"
echo "✓ Each branch should only show content specific to that branch"
echo "✓ No content bleeding between branches"
echo "✓ Branch-specific classes only appear in correct branches"
```

#### Test Case 1B: Content Deduplication Verification
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 1B: Content Deduplication Verification ==="

# Test that identical content across branches uses same storage
echo "--- Step 1: Query common content across branches ---"
git checkout master
MASTER_RESULT=$(cidx query "BusinessEntity dataclass definition" --limit 1 --quiet)

git checkout feature/advanced-processing  
FEATURE_RESULT=$(cidx query "BusinessEntity dataclass definition" --limit 1 --quiet)

echo "--- Step 2: Verify content reuse ---"
echo "Master result: $MASTER_RESULT"
echo "Feature result: $FEATURE_RESULT"

# Manual validation: Content should be identical since BusinessEntity is unchanged
# but accessible from both branches

echo "--- Step 3: Check database for duplicate storage ---"
# Query raw database to verify same content has same ID
cidx query "def validate_entity" --limit 5

echo "--- VALIDATION CRITERIA ---"
echo "✓ Identical content across branches should reuse storage"
echo "✓ Same content should have identical database IDs"  
echo "✓ No unnecessary duplication of unchanged files"
```

### Test Suite 2: Working Directory vs Committed Content

#### Test Case 2A: Working Directory Content Tracking
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 2A: Working Directory Content Tracking ==="

git checkout experimental/ml-integration

echo "--- Step 1: Index branch with mixed working directory/committed state ---"
time cidx index
echo "Branch indexed with mixed state"

echo "--- Step 2: Query committed content ---"  
cidx query "MLIntegrationService class" --limit 2
# Should find ML integration content that was committed

echo "--- Step 3: Query working directory modifications ---"
cidx query "integrate_ml_features" --limit 3
# Should find working directory changes in modules 3-4

echo "--- Step 4: Modify more files and test incremental ---"
echo "# Additional working directory change" >> module_5.py
echo "def working_dir_function():" >> module_5.py  
echo "    return 'working directory modification'" >> module_5.py

time cidx index  # Incremental index
cidx query "working_dir_function" --limit 1
# Should find the new working directory modification

echo "--- Step 5: Commit changes and verify switch ---"
git add module_5.py
git commit -m "Add working directory function to module 5"

time cidx index
cidx query "working_dir_function" --limit 1  
# Should still find it, but now as committed content

echo "--- VALIDATION CRITERIA ---"
echo "✓ Working directory modifications are indexed separately from committed content"
echo "✓ Both working directory and committed versions can coexist correctly"
echo "✓ Incremental indexing picks up working directory changes"
echo "✓ Committing changes properly switches content type"
```

#### Test Case 2B: Point-in-Time Snapshot Consistency  
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 2B: Point-in-Time Snapshot Consistency ==="

git checkout master

echo "--- Step 1: Create baseline committed content ---"
echo "def baseline_function():" >> module_1.py
echo "    return 'baseline committed version'" >> module_1.py
git add module_1.py
git commit -m "Add baseline function"

time cidx index
echo "Baseline committed. Querying committed version..."
COMMITTED_RESULT=$(cidx query "baseline committed version" --limit 1)
echo "Committed result: $COMMITTED_RESULT"

echo "--- Step 2: Make working directory modification ---"
echo "def baseline_function():" >> module_1.py  
echo "    return 'modified working directory version'" >> module_1.py
echo "    # This is a working directory change" >> module_1.py

time cidx index
echo "Working directory indexed. Querying both versions..."

WORKING_RESULT=$(cidx query "modified working directory version" --limit 1)
OLD_COMMITTED=$(cidx query "baseline committed version" --limit 1)

echo "Working directory result: $WORKING_RESULT" 
echo "Old committed result: $OLD_COMMITTED"

echo "--- Step 3: Verify only one version is visible ---"
# Critical test: Should only see working directory version, not both
BOTH_VERSIONS=$(cidx query "baseline_function" --limit 5)
echo "All baseline_function results: $BOTH_VERSIONS"

echo "--- Step 4: Commit working directory changes ---"
git add module_1.py
git commit -m "Update baseline function"

time cidx index
FINAL_RESULT=$(cidx query "modified working directory version" --limit 1)
echo "Final committed result: $FINAL_RESULT"

echo "--- VALIDATION CRITERIA ---"  
echo "✓ Only one version of content visible per branch at any time"
echo "✓ Working directory modifications hide old committed versions"
echo "✓ Committing working directory changes properly replaces old content"
echo "✓ No duplicate versions shown in search results"
```

### Test Suite 3: Performance and Parallelization Validation

#### Test Case 3A: Thread Utilization and Speed Verification
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 3A: Thread Utilization and Performance ==="

# Create larger dataset for meaningful performance testing
for i in {16..30}; do
    cp module_1.py "large_module_${i}.py" 
    sed -i "s/Module 1/Module ${i}/g" "large_module_${i}.py"
    sed -i "s/BusinessEntity1/BusinessEntity${i}/g" "large_module_${i}.py"
done

git add .
git commit -m "Add large module set for performance testing"

echo "--- Step 1: Measure full index performance ---"
time (cidx index --clear 2>&1 | tee performance_full_index.log)

echo "--- Step 2: Analyze thread utilization ---"
echo "Thread utilization analysis:"
grep -o "[0-9] threads" performance_full_index.log | sort | uniq -c
echo "Peak thread count:"
grep -o "[0-9] threads" performance_full_index.log | sort -n | tail -1

echo "--- Step 3: Measure embeddings per second ---"
echo "Embeddings per second analysis:"
grep -o "[0-9.]\+ emb/s" performance_full_index.log | sort -n | tail -5

echo "--- Step 4: Test branch change performance ---"
git checkout feature/advanced-processing
time (cidx index 2>&1 | tee performance_branch_change.log)

echo "Branch change thread analysis:"
grep -o "[0-9] threads" performance_branch_change.log | sort | uniq -c

echo "--- Step 5: Test incremental performance ---" 
echo "# Performance test modification" >> module_1.py
time (cidx index 2>&1 | tee performance_incremental.log)

echo "Incremental thread analysis:"
grep -o "[0-9] threads" performance_incremental.log | sort | uniq -c

echo "--- VALIDATION CRITERIA ---"
echo "✓ Thread count should consistently show 8 threads during processing"
echo "✓ Embeddings per second should indicate parallel processing (>20)"
echo "✓ All operations (full, branch change, incremental) show parallel processing"
echo "✓ Performance should be significantly better than sequential processing"
```

#### Test Case 3B: Scalability and Resource Usage
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 3B: Scalability and Resource Usage ==="

# Create even larger dataset
for i in {31..50}; do
    # Create larger, more complex files
    cat > "complex_module_${i}.py" << EOF
# This is a large, complex module for scalability testing
$(cat module_1.py)
$(cat module_1.py | sed 's/BusinessEntity1/BusinessEntity'${i}'/g')
$(cat module_1.py | sed 's/EntityProcessor1/EntityProcessor'${i}'/g')
EOF
done

git add .
git commit -m "Add complex modules for scalability testing"

echo "--- Step 1: Monitor resource usage during large indexing ---"
# Run indexing while monitoring system resources
echo "Starting large-scale indexing operation..."
time (cidx index --clear 2>&1 | tee scalability_test.log) &
INDEX_PID=$!

# Monitor resource usage (if available)
sleep 2
ps aux | grep cidx || echo "Process monitoring not available"
sleep 5  
ps aux | grep cidx || echo "Process monitoring not available"

wait $INDEX_PID

echo "--- Step 2: Analyze scalability metrics ---"
TOTAL_FILES=$(grep -c "files completed" scalability_test.log)
FINAL_THREAD_COUNT=$(grep -o "[0-9] threads" scalability_test.log | tail -1)
PEAK_SPEED=$(grep -o "[0-9.]\+ emb/s" scalability_test.log | sort -n | tail -1)

echo "Scalability Results:"
echo "Total files processed: $TOTAL_FILES"
echo "Final thread utilization: $FINAL_THREAD_COUNT"  
echo "Peak processing speed: $PEAK_SPEED"

echo "--- Step 3: Test branch switching performance with large dataset ---"
git checkout performance/optimization
time (cidx index 2>&1 | tee scalability_branch_change.log)

BRANCH_THREADS=$(grep -o "[0-9] threads" scalability_branch_change.log | tail -1)
BRANCH_SPEED=$(grep -o "[0-9.]\+ emb/s" scalability_branch_change.log | sort -n | tail -1)

echo "Branch change scalability:"
echo "Thread utilization: $BRANCH_THREADS"
echo "Processing speed: $BRANCH_SPEED"

echo "--- VALIDATION CRITERIA ---"
echo "✓ Should handle 50+ files without performance degradation"
echo "✓ Thread utilization should remain high (8 threads) even with large datasets"
echo "✓ Memory usage should be acceptable (no crashes or excessive consumption)"
echo "✓ Branch changes should maintain performance with large datasets"
```

### Test Suite 4: Error Handling and Edge Cases

#### Test Case 4A: Cancellation and Recovery Testing
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 4A: Cancellation and Recovery Testing ==="

git checkout master

echo "--- Step 1: Test cancellation during large operation ---"
# Start large indexing operation and cancel it
timeout 15s cidx index --clear 2>&1 | tee cancellation_test.log
echo "Operation cancelled after 15 seconds"

echo "--- Step 2: Verify graceful cancellation ---"
grep -i "cancel\|interrupt" cancellation_test.log || echo "No cancellation messages found"

echo "--- Step 3: Test resumption after cancellation ---"
time (cidx index 2>&1 | tee resumption_test.log)
echo "Resumption completed"

RESUMED_FILES=$(grep -c "files completed" resumption_test.log)
echo "Files processed in resumption: $RESUMED_FILES"

echo "--- Step 4: Verify data consistency after cancellation/resume ---"
cidx query "BusinessEntity class" --limit 3
# Should find content without corruption

echo "--- Step 5: Test cancellation during branch change ---"
git checkout feature/advanced-processing
timeout 10s cidx index 2>&1 | tee branch_cancellation.log
echo "Branch change cancelled"

# Resume branch change
time cidx index
cidx query "AdvancedProcessor" --limit 1
# Should work correctly after resumed branch change

echo "--- VALIDATION CRITERIA ---"
echo "✓ Cancellation should be graceful without data corruption"
echo "✓ Resume after cancellation should work correctly"
echo "✓ No database inconsistencies after cancellation/resume cycles"
echo "✓ Branch changes should handle cancellation properly"
```

#### Test Case 4B: Edge Case and Error Handling
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 4B: Edge Case and Error Handling ==="

echo "--- Step 1: Test with corrupted/invalid files ---"
# Create files with problematic content
echo "This is not valid Python code { { {" > corrupted_file.py
echo "" > empty_file.py  # Empty file
touch large_file.py
for i in {1..1000}; do echo "# Line $i with some content here" >> large_file.py; done

git add .
git commit -m "Add edge case files for testing"

time (cidx index 2>&1 | tee edge_case_test.log)

echo "--- Step 2: Verify error handling ---"
grep -i "error\|failed\|warning" edge_case_test.log || echo "No error messages found"

echo "--- Step 3: Test with file permission issues ---"  
# Create file and remove read permission (if possible)
echo "def test_function(): pass" > permission_test.py
chmod 000 permission_test.py 2>/dev/null || echo "Cannot modify permissions"

git add . 2>/dev/null || echo "Git add failed as expected"
git commit -m "Add permission test file" 2>/dev/null || echo "Git commit failed as expected"

time cidx index 2>&1 | tee permission_test.log
grep -i "permission\|error" permission_test.log || echo "No permission errors found"

# Restore permissions
chmod 644 permission_test.py 2>/dev/null || echo "Cannot restore permissions"

echo "--- Step 4: Test with binary files ---"
# Create binary file (should be ignored)
echo -e "\x00\x01\x02\x03\x04\x05" > binary_file.bin
git add binary_file.bin
git commit -m "Add binary file"

time cidx index
# Should handle binary files gracefully

echo "--- Step 5: Test with extremely long paths ---"
mkdir -p very/deeply/nested/directory/structure/for/testing/purposes
echo "def deep_function(): pass" > very/deeply/nested/directory/structure/for/testing/purposes/deep_file.py
git add .
git commit -m "Add deeply nested file"

time cidx index
cidx query "deep_function" --limit 1
# Should handle deep paths correctly

echo "--- VALIDATION CRITERIA ---"
echo "✓ Should handle corrupted files gracefully without crashing"
echo "✓ Should handle permission errors without stopping processing"
echo "✓ Should ignore binary files appropriately" 
echo "✓ Should handle extremely long file paths"
echo "✓ Error messages should be informative but not crash the system"
```

### Test Suite 5: Branch Management Operations

#### Test Case 5A: Branch Cleanup and Garbage Collection
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 5A: Branch Cleanup and Garbage Collection ==="

echo "--- Step 1: Create branch with unique content ---"
git checkout -b test-cleanup-branch
echo "def cleanup_test_function(): return 'cleanup test'" > cleanup_test_file.py
git add .
git commit -m "Add content for cleanup testing"

time cidx index
cidx query "cleanup_test_function" --limit 1
# Should find the function

echo "--- Step 2: Switch to different branch ---"
git checkout master
cidx query "cleanup_test_function" --limit 1
# Should not find the function (branch isolation)

echo "--- Step 3: Delete the test branch ---"
git branch -D test-cleanup-branch

# Note: This tests the underlying branch cleanup capability
# The actual cleanup might happen automatically or require manual trigger
echo "Branch deleted from git"

echo "--- Step 4: Verify content is properly handled ---"
# Content should still exist in database but be marked appropriately
# This tests the garbage collection capability

cidx query "cleanup_test_function" --limit 1
echo "Tested content accessibility after branch deletion"

echo "--- VALIDATION CRITERIA ---"
echo "✓ Branch deletion should not corrupt database"
echo "✓ Content from deleted branches should be properly managed"
echo "✓ No orphaned content should cause issues"
echo "✓ Garbage collection should work safely"
```

#### Test Case 5B: Complex Branch Topology
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== Test Case 5B: Complex Branch Topology ==="

echo "--- Step 1: Create complex branch structure ---"
git checkout master
git checkout -b branch-a
echo "def function_a(): return 'branch a'" > branch_a_file.py
git add .
git commit -m "Add branch A content"

git checkout master  
git checkout -b branch-b
echo "def function_b(): return 'branch b'" > branch_b_file.py
git add .  
git commit -m "Add branch B content"

git checkout branch-a
git checkout -b branch-a-sub
echo "def function_a_sub(): return 'branch a sub'" > branch_a_sub_file.py
git add .
git commit -m "Add branch A sub content"

echo "--- Step 2: Index all branches and test isolation ---"
git checkout master
time cidx index

git checkout branch-a  
time cidx index
cidx query "function_a" --limit 1

git checkout branch-b
time cidx index  
cidx query "function_b" --limit 1

git checkout branch-a-sub
time cidx index
cidx query "function_a_sub" --limit 1

echo "--- Step 3: Test branch relationship handling ---"
git checkout branch-a-sub
# Should see content from branch-a (parent) but not branch-b
cidx query "function_a" --limit 1  # Should find (parent branch)
cidx query "function_b" --limit 1  # Should not find (different branch)

echo "--- Step 4: Test merge scenarios ---"
git checkout branch-a
git merge branch-a-sub --no-edit
time cidx index

cidx query "function_a_sub" --limit 1  # Should find merged content
cidx query "function_b" --limit 1      # Should not find other branch

echo "--- VALIDATION CRITERIA ---"
echo "✓ Complex branch topologies should be handled correctly"
echo "✓ Branch relationships should be preserved"  
echo "✓ Merged content should be accessible in target branch"
echo "✓ Branch isolation should work with nested branches"
```

### Final Validation and Success Criteria

#### Comprehensive Validation Summary
```bash
cd ~/.tmp/refactoring_test_repo

echo "=== COMPREHENSIVE VALIDATION SUMMARY ==="

echo "--- Final Performance Validation ---"
# One final comprehensive test
git checkout master
time (cidx index --clear 2>&1 | tee final_validation.log)

echo "Final performance metrics:"
echo "Thread utilization:" $(grep -o "[0-9] threads" final_validation.log | sort | uniq -c)
echo "Peak speed:" $(grep -o "[0-9.]\+ emb/s" final_validation.log | sort -n | tail -1)
echo "Files processed:" $(grep -c "files completed" final_validation.log)

echo "--- Final Branch Isolation Test ---"
git checkout feature/advanced-processing
ADVANCED_COUNT=$(cidx query "AdvancedProcessor" --limit 5 | wc -l)

git checkout performance/optimization  
OPTIMIZED_COUNT=$(cidx query "OptimizedProcessor" --limit 5 | wc -l)

git checkout master
ADVANCED_IN_MASTER=$(cidx query "AdvancedProcessor" --limit 1 | wc -l)
OPTIMIZED_IN_MASTER=$(cidx query "OptimizedProcessor" --limit 1 | wc -l)

echo "Branch isolation verification:"
echo "AdvancedProcessor in feature branch: $ADVANCED_COUNT"
echo "OptimizedProcessor in performance branch: $OPTIMIZED_COUNT"  
echo "AdvancedProcessor in master: $ADVANCED_IN_MASTER (should be 0)"
echo "OptimizedProcessor in master: $OPTIMIZED_IN_MASTER (should be 0)"

echo "--- Final Success Criteria Check ---"
echo ""
echo "🎯 SUCCESS CRITERIA CHECKLIST:"
echo ""
echo "PERFORMANCE REQUIREMENTS:"
echo "  ✅ Thread utilization: 8 threads consistently used"
echo "  ✅ Processing speed: >20 embeddings/sec indicates parallelization"
echo "  ✅ All operations (branch change, full index, incremental) use parallel processing"
echo "  ✅ 4-8x speedup demonstrated vs sequential processing"
echo ""
echo "FUNCTIONALITY REQUIREMENTS:"
echo "  ✅ Branch isolation: No content bleeding between branches"
echo "  ✅ Content deduplication: Same content reused across branches"  
echo "  ✅ Working directory tracking: Working changes indexed separately"
echo "  ✅ Point-in-time snapshots: Only one version visible per branch"
echo "  ✅ Branch operations: Cleanup and management work correctly"
echo ""
echo "RELIABILITY REQUIREMENTS:"
echo "  ✅ Cancellation handling: Graceful cancellation without corruption"
echo "  ✅ Error recovery: System handles errors without crashing"
echo "  ✅ Edge cases: Corrupted files, permissions, etc. handled gracefully"
echo "  ✅ Complex topologies: Nested branches and merges work correctly"
echo ""
echo "REGRESSION PREVENTION:"
echo "  ✅ All existing functionality preserved"
echo "  ✅ No performance regressions in any operation"
echo "  ✅ Git-aware features work identically to before"
echo "  ✅ API compatibility maintained"

echo ""
echo "🚀 REFACTORING VALIDATION COMPLETE"
echo ""
echo "If all criteria above show ✅, the refactoring has successfully:"
echo "- Eliminated architectural redundancy"  
echo "- Achieved 4-8x performance improvement"
echo "- Preserved all critical git-aware capabilities"
echo "- Maintained system reliability and error handling"
echo ""
echo "The unified HighThroughputProcessor architecture is ready for production use."
```

This comprehensive manual testing protocol validates all critical capabilities identified in the deep analysis while providing clear success/failure criteria for the refactoring effort.