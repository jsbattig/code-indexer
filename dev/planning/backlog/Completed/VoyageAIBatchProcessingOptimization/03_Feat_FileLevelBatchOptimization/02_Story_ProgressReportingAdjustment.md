# Story: Progress Reporting Adjustment for Batch Operations

## 📖 User Story

As a user monitoring indexing progress, I want progress reporting to remain smooth and accurate despite internal batch processing so that the user experience is identical to before while benefiting from dramatically improved processing speed.

## 🎯 Business Value

After this story completion, users will experience the same responsive progress reporting they're accustomed to, but with much faster overall processing due to batch optimization, maintaining excellent user experience while delivering performance benefits.

## 📍 Implementation Target

**File**: `/src/code_indexer/services/file_chunking_manager.py`  
**Lines**: 196-204 and other progress callback locations in `_process_file_clean_lifecycle()`

## ✅ Acceptance Criteria

### Scenario: Progress calculation accuracy with batch processing
```gherkin
Given file processing using batch operations instead of individual chunks
When progress callbacks are triggered during file processing
Then progress percentages should remain accurate for overall file count
And file completion tracking should reflect actual file completion status
And progress updates should occur at appropriate intervals for user feedback
And total file count and completed file count should be consistent

Given a processing session with 50 files being indexed
When batch processing completes files at different rates
Then progress should show accurate X/50 files completed
And percentage calculation should be correct (completed/total * 100)
And progress updates should be smooth despite internal batching differences
And final progress should reach exactly 100% when all files complete
```

### Scenario: File-level progress granularity adjustment
```gherkin
Given the shift from chunk-level to file-level batch processing
When progress reporting needs to account for batch completion timing
Then progress updates should occur when entire files complete (not individual chunks)
And file completion should trigger progress callback with updated counts
And progress smoothness should be maintained despite larger completion increments
And users should experience responsive feedback throughout processing

Given files of varying sizes processed as batches
When small files (few chunks) complete quickly and large files take longer
Then progress reporting should handle variable completion timing gracefully
And overall progress should remain predictable and smooth for users
And processing speed indicators should reflect the improved batch performance
```

### Scenario: Concurrent files data integration with batch processing
```gherkin
Given the CleanSlotTracker managing concurrent file processing state
When files are processed using batch operations
Then concurrent files display should accurately reflect batch processing status
And slot utilization should be correctly reported for batch operations
And file status updates should align with batch processing completion
And real-time file tracking should work correctly with batch timing

Given concurrent file processing with batch operations
When the slot tracker provides concurrent files data for display
Then file processing states should be accurate (processing, completed)
And active thread information should reflect batch processing workload
And file names and processing states should update appropriately
And progress display should show meaningful status for batch operations
```

### Scenario: Performance metrics accuracy with batch processing
```gherkin
Given batch processing improving overall throughput significantly
When progress reporting includes performance metrics (files/s, KB/s, threads)
Then files per second should reflect the improved processing rate
And KB per second should accurately represent data processing throughput
And thread utilization should be reported accurately for batch processing
And performance improvements should be visible to users in real-time

Given the dramatic throughput improvements from batch processing
When progress information includes speed metrics
Then speed calculations should account for batch processing efficiency
And metrics should reflect the true performance improvements achieved
And users should see evidence of the optimization through better speeds
And progress reporting should showcase the performance benefits clearly
```

## 🔧 Technical Implementation Details

### Progress Callback Timing Changes
```pseudocode
# Current: Progress update per chunk completion (removed)
# for each chunk completion:
#     progress_callback(completed_chunks, total_chunks, ...)

# New: Progress update per file completion (implement)
# when file batch processing completes:
progress_callback(
    completed_files,      # Increment when entire file completes
    total_files,          # Total files to process
    file_path,           # Current completed file
    info=progress_info,   # Include batch processing performance metrics
    concurrent_files=concurrent_files_data
)
```

### Progress Information Enhancement
```pseudocode
# Enhanced progress info reflecting batch performance
progress_info = (
    f"{completed_files}/{total_files} files ({percentage}%) | "
    f"{files_per_second:.1f} files/s | "    # Improved due to batching
    f"{kb_per_second:.1f} KB/s | "          # Improved throughput
    f"{active_threads} threads | "
    f"{current_file.name}"
)
```

### Concurrent Files Integration
- **Slot Tracker Integration**: Use existing CleanSlotTracker for real-time state
- **Batch Status Reporting**: Update file status when batch completes
- **Thread Utilization**: Accurately report thread usage for batch operations
- **Real-time Updates**: Maintain responsive concurrent file display

## 🧪 Testing Requirements

### Progress Accuracy Validation
- [ ] Progress percentages accurate throughout processing
- [ ] File completion counts correct with batch processing
- [ ] Final progress reaches exactly 100% on completion
- [ ] Progress updates occur at appropriate intervals

### User Experience Testing
- [ ] Progress reporting remains smooth and responsive
- [ ] Performance metrics reflect batch processing improvements
- [ ] Concurrent files display updates correctly
- [ ] No significant changes in progress reporting behavior from user perspective

### Performance Integration Testing
- [ ] Speed metrics (files/s, KB/s) show improved performance
- [ ] Thread utilization reported accurately during batch processing
- [ ] Progress reporting overhead minimal despite batch operations
- [ ] Large codebase processing shows smooth progress throughout

## 🎯 User Experience Preservation

### Progress Smoothness
- **Update Frequency**: File-level updates instead of chunk-level
- **Responsive Feedback**: Maintain user perception of active processing
- **Completion Accuracy**: Ensure 100% completion is reached reliably
- **Performance Visibility**: Show users the benefits of optimization

### Information Quality
- **Accurate Metrics**: Files/s and KB/s should reflect true performance
- **Meaningful Status**: File processing status should be clear and accurate
- **Thread Information**: Thread utilization should be reported correctly
- **Real-time Updates**: Concurrent processing information should be current

## ⚠️ Implementation Considerations

### Granularity Changes
- **File-Level Updates**: Progress updates when files complete (not chunks)
- **Batch Timing**: Variable completion timing due to different file sizes
- **Smoothness Preservation**: Ensure progress doesn't appear to "jump"
- **Performance Benefits**: Show users evidence of improved processing speed

### Existing Integration
- **CleanSlotTracker**: Use existing slot tracking for concurrent files
- **Progress Callback Interface**: Maintain existing callback signature
- **Statistics Integration**: Use existing performance calculation methods
- **Error Reporting**: Maintain existing error reporting through progress

### Performance Metrics Enhancement
- **Throughput Calculation**: Account for batch processing efficiency gains
- **Speed Reporting**: Show improved files/s and KB/s due to optimization
- **Thread Utilization**: Accurate reporting of batch processing thread usage
- **User Satisfaction**: Demonstrate clear performance improvement to users

## 📋 Definition of Done

- [ ] Progress reporting remains smooth and accurate with batch processing
- [ ] File completion tracking works correctly with batch operation timing
- [ ] Progress percentages accurate throughout processing (0% to 100%)
- [ ] Performance metrics (files/s, KB/s) reflect batch processing improvements
- [ ] Concurrent files display integrates correctly with batch operations
- [ ] Progress callback timing adjusted appropriately for file-level completion
- [ ] User experience remains excellent despite internal batch processing changes
- [ ] No regression in progress reporting responsiveness or accuracy
- [ ] Performance improvements visible to users through progress metrics
- [ ] Integration tests demonstrate smooth progress reporting under various load conditions
- [ ] Code review completed and approved

---

**Story Status**: ⏳ Ready for Implementation  
**Estimated Effort**: 3-4 hours  
**Risk Level**: 🟢 Low (Progress reporting adjustments)  
**Dependencies**: 01_Story_FileChunkBatching (file processing changes)  
**User Impact**: 🎯 Maintains excellent user experience while delivering performance benefits  
**Success Measure**: Smooth progress reporting with visible performance improvements