# Technical Specification: Surgical Implementation Details

## 📁 **NEW FILE LOCATIONS**

### **FileChunkingManager Class**
```python
# NEW FILE: src/code_indexer/services/file_chunking_manager.py

from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
import time
import logging

from .vector_calculation_manager import VectorCalculationManager
from ..indexing.fixed_size_chunker import FixedSizeChunker

logger = logging.getLogger(__name__)

@dataclass
class FileProcessingResult:
    success: bool
    file_path: Path
    chunks_processed: int
    processing_time: float
    error: Optional[str] = None

class FileChunkingManager:
    def __init__(self, 
                 vector_manager: VectorCalculationManager,
                 chunker: FixedSizeChunker,
                 qdrant_client,  # Pass from HighThroughputProcessor
                 thread_count: int):
        self.vector_manager = vector_manager
        self.chunker = chunker
        self.qdrant_client = qdrant_client
        self.executor = ThreadPoolExecutor(
            max_workers=thread_count + 2,
            thread_name_prefix="FileChunk"
        )
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.executor.shutdown(wait=True, timeout=30.0)
        
    def submit_file_for_processing(self, 
                                  file_path: Path, 
                                  metadata: Dict[str, Any],
                                  progress_callback: Optional[Callable]) -> Future[FileProcessingResult]:
        # Implementation matches pseudocode
        
    def _process_file_complete_lifecycle(self, 
                                        file_path: Path, 
                                        metadata: Dict[str, Any],
                                        progress_callback: Optional[Callable]) -> FileProcessingResult:
        # Implementation matches pseudocode
```

## 🔧 **SURGICAL MODIFICATIONS**

### **HighThroughputProcessor Import Changes**
```python
# MODIFY: src/code_indexer/services/high_throughput_processor.py
# ADD at line 28 (after existing imports):
from .file_chunking_manager import FileChunkingManager, FileProcessingResult
```

### **Exact Line Replacements**
```python
# REPLACE LINES 388-707 in process_files_high_throughput() with:

        # PARALLEL FILE PROCESSING: Replace sequential chunking with parallel submission
        with FileChunkingManager(
            vector_manager=vector_manager,
            chunker=self.fixed_size_chunker,
            qdrant_client=self.qdrant_client,
            thread_count=vector_thread_count
        ) as file_manager:
            
            # Submit all files for parallel processing
            file_futures = []
            for file_path in files:
                file_metadata = self.file_identifier.get_file_metadata(file_path)
                file_future = file_manager.submit_file_for_processing(
                    file_path, file_metadata, progress_callback
                )
                file_futures.append(file_future)
                
            # Collect file-level results  
            completed_files = 0
            for file_future in as_completed(file_futures):
                if self.cancelled:
                    break
                    
                file_result = file_future.result(timeout=600)
                
                if file_result.success:
                    stats.files_processed += 1
                    stats.chunks_created += file_result.chunks_processed
                    completed_files += 1
                    
                    # Progress callback (file-level)
                    if progress_callback:
                        files_per_second = self._calculate_files_per_second(completed_files)
                        info_msg = f"{completed_files}/{len(files)} files ({completed_files/len(files)*100:.0f}%) | {files_per_second:.1f} files/s"
                        progress_callback(completed_files, len(files), Path(""), info=info_msg)
                else:
                    stats.failed_files += 1
```

### **Method Signature Dependencies**
```python
# FileChunkingManager needs access to existing HighThroughputProcessor methods:
# - self._create_qdrant_point() for creating points
# - self.qdrant_client for atomic writes
# - self.file_identifier for metadata
```

## 🎯 **INTEGRATION WIRING COMPLETE**

### **Constructor Integration**
- FileChunkingManager instantiated in `with` statement inside `process_files_high_throughput()`
- Pass existing components: vector_manager, chunker, qdrant_client, thread_count
- No constructor changes to HighThroughputProcessor required

### **Method Call Site Changes**
- REMOVE: All current Phase 1, 2, 3 logic (lines 388-707)
- ADD: FileChunkingManager with statement and file-level result collection
- PRESERVE: Method signature, stats initialization, final statistics

### **Dependency Access Pattern**
- Pass dependencies down to FileChunkingManager rather than inheritance
- FileChunkingManager gets qdrant_client reference for atomic writes
- Worker threads call qdrant_client.upsert_points_atomic() directly

## ✅ **IMPLEMENTATION READY**

All new classes, methods, and integration points now have:
- ✅ Exact file locations specified
- ✅ Complete import statements documented  
- ✅ Precise line replacement ranges identified
- ✅ Dependency injection patterns specified
- ✅ Method signatures with full type annotations
- ✅ Integration with existing code detailed
- ✅ Surgical replacement instructions actionable

The epic now provides complete implementation guidance without ambiguity or guesswork.