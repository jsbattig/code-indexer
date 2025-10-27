# Surgical Integration Specification: Real-Time File State Updates

## 🔧 **CODE TO BE REMOVED/ALTERED**

### **REMOVE: Broken Synchronous Callback Implementation**

**File:** `src/code_indexer/services/file_chunking_manager.py`

**DELETE Lines 178-202** (complete _update_file_status callback implementation):
```python
# DELETE THIS ENTIRE BLOCK:
        # FULL PROGRESS CALLBACK ON EVERY STATE CHANGE - LOCK FREE
        if self.progress_callback and self.progress_state and self.file_tracker:
            try:
                # Read shared state without locks (lock-free reads)
                completed_files = self.progress_state['completed_files_counter']['count']
                total_files = self.progress_state['total_files'] 
                concurrent_files = self.file_tracker.get_concurrent_files_data()
                
                # Simple calculations without locks
                file_progress_pct = (completed_files / total_files * 100) if total_files > 0 else 0
                
                # Create basic info message without complex calculations
                info_msg = f"{completed_files}/{total_files} files ({file_progress_pct:.0f}%) | {self.progress_state['thread_count']} threads"
                
                # TRIGGER FULL PROGRESS CALLBACK
                self.progress_callback(
                    completed_files,     # Real current count
                    total_files,         # Real total count  
                    Path(""),           # Empty path
                    info=info_msg,      # Progress string
                    concurrent_files=concurrent_files  # All file states
                )
            except Exception as e:
                # Don't let callback failures break file processing
                logger.warning(f"Progress callback failed: {e}")
```

### **REMOVE: Shared Progress State Infrastructure**

**File:** `src/code_indexer/services/high_throughput_processor.py`

**DELETE Lines 401-407** (shared progress state creation):
```python
# DELETE THIS ENTIRE BLOCK:
        # Create shared progress state for full progress calculations in workers (lock-free)
        completed_files_counter = {'count': 0}  # Remove lock
        shared_progress_state = {
            'completed_files_counter': completed_files_counter,
            'total_files': len(files),
            'thread_count': vector_thread_count,
        }
```

**DELETE Line 424** (progress_state parameter):
```python
# DELETE THIS LINE:
                progress_state=shared_progress_state,  # SHARED STATE FOR CALCULATIONS
```

### **REMOVE: Shared Counter Increment**

**File:** `src/code_indexer/services/file_chunking_manager.py`

**DELETE Lines 463-465** (shared counter increment):
```python
# DELETE THESE LINES:
                # Increment shared completed files counter (lock-free)
                if self.progress_state:
                    self.progress_state['completed_files_counter']['count'] += 1
```

**DELETE Line 61** (progress_state parameter):
```python
# DELETE THIS LINE:
        progress_state: Optional[Dict] = None,  # SHARED PROGRESS STATE
```

**DELETE Line 92** (progress_state storage):
```python
# DELETE THIS LINE:
        self.progress_state = progress_state  # SHARED PROGRESS STATE FOR CALCULATIONS
```

## 🔧 **NEW CODE INTEGRATION POINTS**

### **ADD: AsyncDisplayWorker Import and Integration**

**File:** `src/code_indexer/services/high_throughput_processor.py`

**ADD after line 30:**
```python
from ..progress.async_display_worker import AsyncDisplayWorker
```

**REPLACE Lines 413-424** (FileChunkingManager instantiation):
```python
# REPLACE WITH:
                # Create async display worker for real-time state updates
                display_worker = AsyncDisplayWorker(
                    file_tracker=self.file_tracker,
                    progress_callback=progress_callback,
                    thread_count=vector_thread_count,
                    total_files=len(files)
                )
                
                # Start async display processing
                display_worker.start()
                
                try:
                    with FileChunkingManager(
                        vector_manager=vector_manager,
                        chunker=self.fixed_size_chunker,
                        qdrant_client=self.qdrant_client,
                        thread_count=vector_thread_count,
                        file_tracker=self.file_tracker,
                        display_worker=display_worker,  # NEW: Async display integration
                    ) as file_manager:
```

**ADD after file processing block ends:**
```python
                finally:
                    # Stop async display worker
                    display_worker.stop()
```

### **MODIFY: FileChunkingManager Constructor**

**File:** `src/code_indexer/services/file_chunking_manager.py`

**REPLACE Lines 60-61**:
```python
# FROM:
        progress_callback: Optional[Callable] = None,
        progress_state: Optional[Dict] = None,  # SHARED PROGRESS STATE

# TO:
        display_worker: Optional["AsyncDisplayWorker"] = None,
```

**REPLACE Line 92**:
```python
# FROM:
        self.progress_state = progress_state  # SHARED PROGRESS STATE FOR CALCULATIONS

# TO:
        self.display_worker = display_worker
```

### **REPLACE: _update_file_status Implementation**

**File:** `src/code_indexer/services/file_chunking_manager.py`

**REPLACE Lines 173-202** (entire method):
```python
    def _update_file_status(self, thread_id: int, status: FileStatus, status_text: Optional[str] = None):
        """Update file status with async display trigger."""
        # Update central state store
        if self.file_tracker:
            self.file_tracker.update_file_status(thread_id, status)
        
        # Async display update (immediate non-blocking return)
        if self.display_worker:
            self.display_worker.queue_state_change(thread_id, status)
```

### **REMOVE: All Direct Progress Callback Usage**

**File:** `src/code_indexer/services/high_throughput_processor.py`

**DELETE/COMMENT OUT Lines 477-542** (existing progress callback in main thread):
```python
# REMOVE OR COMMENT OUT - Replaced by AsyncDisplayWorker
# The async display worker handles all progress updates
# This synchronous callback is no longer needed
```

## 🗂️ **NEW FILE CREATION**

### **CREATE: AsyncDisplayWorker Implementation**

**New File:** `src/code_indexer/progress/async_display_worker.py`
- Complete AsyncDisplayWorker class implementation
- StateChangeEvent data structure
- Queue-based event processing
- Real progress calculations
- Overflow protection

### **CREATE: Test Suite**

**New File:** `tests/unit/progress/test_async_display_worker.py`
- Comprehensive test coverage for AsyncDisplayWorker
- Event queuing and processing tests
- Progress calculation accuracy tests
- Integration tests with ConsolidatedFileTracker

## 🔄 **INTEGRATION FLOW**

**Data Flow After Integration:**
```
1. Worker Thread → _update_file_status() → ConsolidatedFileTracker.update_file_status()
2. Worker Thread → _update_file_status() → AsyncDisplayWorker.queue_state_change()
3. AsyncDisplayWorker → Reads ConsolidatedFileTracker → Calculates Complete Progress
4. AsyncDisplayWorker → progress_callback() → CLI Display Update
```

**File Removal/Modification Summary:**
- **Remove**: 50+ lines of broken synchronous callback code
- **Remove**: Shared progress state infrastructure  
- **Remove**: Lock-based calculation attempts
- **Add**: AsyncDisplayWorker class (~200 lines)
- **Modify**: FileChunkingManager integration (10 lines)
- **Modify**: HighThroughputProcessor integration (20 lines)

## 🎯 **VALIDATION CRITERIA**

**After Integration:**
- **Real-time state updates** visible in fixed N-line display
- **Complete progress calculations** (files/s, KB/s, percentages) with real data
- **Non-blocking worker threads** maintaining parallel processing performance  
- **All 14 worker states** visible with immediate updates
- **No deadlocks** or performance regressions

This surgical integration replaces the broken synchronous approach with proper async architecture while preserving all existing parallel processing functionality.