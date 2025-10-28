# Story 2: Aggregate Metrics Line

## User Story

**As a developer monitoring overall processing performance**, I want a dedicated metrics line showing files/s, KB/s, and active thread count, so that I can understand the aggregate performance characteristics of the multi-threaded processing operation.

## Acceptance Criteria

### Given multi-threaded file processing is active
### When the aggregate metrics line is displayed
### Then I should see current files per second processing rate
### And I should see current kilobytes per second throughput rate
### And I should see active thread count reflecting current worker utilization
### And metrics should be clearly formatted and easily readable
### And the metrics line should be separate from the progress bar line

### Given processing performance changes during operation
### When files/s rate increases due to parallel processing efficiency
### Then the files/s metric should update in real-time to reflect new rate
### And KB/s metric should update to reflect cumulative throughput changes
### And thread count should update to reflect actual worker activity
### And metrics should provide meaningful insights into parallel processing benefits

## Technical Requirements

### Pseudocode Implementation
```
AggregateMetricsManager:
    calculate_current_metrics():
        files_per_second = calculate_files_rate()
        kb_per_second = calculate_kb_throughput()  
        active_threads = get_active_thread_count()
        return format_metrics_line(files_per_second, kb_per_second, active_threads)
    
    format_metrics_line(files_rate, kb_rate, thread_count):
        return f"{files_rate:.1f} files/s | {kb_rate:.1f} KB/s | {thread_count} threads"
    
    update_metrics_display():
        current_metrics = calculate_current_metrics()
        update_metrics_line_display(current_metrics)
```

### Visual Format
```
Line 1: Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 37% • 0:01:23 • 0:02:12 • 45/120 files
Line 2: 12.3 files/s | 456.7 KB/s | 8 threads
```

### Metrics Requirements
- **Files/s**: Real-time file processing rate with rolling window smoothing
- **KB/s**: Source data throughput rate showing data ingestion speed  
- **Threads**: Current active worker thread count (0-8)
- **Format**: Clean separation with pipe (|) delimiters
- **Updates**: Real-time refresh reflecting current processing state

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] Files/s metric displays current file processing rate
- [ ] KB/s metric displays current data throughput rate
- [ ] Active thread count displays current worker utilization
- [ ] Metrics are clearly formatted and easily readable
- [ ] Metrics line is separate from progress bar line
- [ ] Files/s updates in real-time reflecting processing changes
- [ ] KB/s updates reflecting cumulative throughput changes
- [ ] Thread count updates reflecting actual worker activity
- [ ] Metrics provide insights into parallel processing benefits

## Testing Requirements

### Unit Tests Required:
- Files/s calculation accuracy and real-time updates
- KB/s calculation accuracy and cumulative tracking
- Thread count accuracy and active worker reflection
- Metrics line formatting consistency

### Integration Tests Required:
- Real-time metrics updates during multi-threaded processing
- Metrics accuracy validation against actual processing performance
- Parallel processing benefits visibility through metrics