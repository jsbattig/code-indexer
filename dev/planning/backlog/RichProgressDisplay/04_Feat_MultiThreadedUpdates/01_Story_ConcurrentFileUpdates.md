# Story 1: Concurrent File Updates

## User Story

**As a developer monitoring multi-threaded file processing**, I want to see real-time updates for all files being processed simultaneously by different worker threads, so that I can observe the parallel processing activity and understand system utilization.

## Acceptance Criteria

### Given 8 worker threads are processing files simultaneously
### When multiple files are being processed concurrently
### Then I should see up to 8 individual file lines displayed simultaneously
### And each file line should update independently in real-time
### And elapsed time should increment for each file being processed
### And file lines should appear immediately when threads start processing
### And file lines should update without interfering with each other
### And the number of displayed file lines should match active thread count

### Given worker threads complete and start new files
### When some threads finish while others continue processing
### Then completed files should show "complete" status
### And new files should appear as threads pick up additional work
### And the display should handle dynamic file line changes smoothly
### And thread utilization should be clearly visible through active file count

## Technical Requirements

### Pseudocode Implementation
```
ConcurrentFileUpdateManager:
    active_files = ThreadSafeDict()  # file_id -> FileProgress
    display_lock = threading.Lock()
    
    start_file_processing(file_id, file_path, thread_id):
        with display_lock:
            file_progress = create_file_progress(file_path, current_time)
            active_files[file_id] = file_progress
            trigger_display_update()
    
    update_file_elapsed_time():
        # Called every second to update all active files
        with display_lock:
            current_time = get_current_time()
            for file_id, progress in active_files.items():
                if progress.status == "processing":
                    progress.elapsed_time = current_time - progress.start_time
            trigger_display_update()
    
    complete_file_processing(file_id):
        with display_lock:
            if file_id in active_files:
                active_files[file_id].status = "complete"
                active_files[file_id].completion_time = current_time
                trigger_display_update()
                schedule_file_removal(file_id, current_time + 3.0)
```

### Concurrent Display Example
```
Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 37% • 0:01:23 • 0:02:12 • 45/120 files
12.3 files/s | 456.7 KB/s | 8 threads
├─ utils.py (2.1 KB, 5s) vectorizing...      ← Thread 1
├─ config.py (1.8 KB, 3s) complete           ← Thread 2 (just finished)
├─ main.py (3.4 KB, 7s) vectorizing...       ← Thread 3  
├─ auth.py (1.2 KB, 2s) vectorizing...       ← Thread 4
├─ models.py (4.7 KB, 4s) vectorizing...     ← Thread 5
├─ tests.py (6.3 KB, 6s) vectorizing...      ← Thread 6
├─ services.py (2.9 KB, 1s) vectorizing...   ← Thread 7
├─ handlers.py (5.1 KB, 8s) vectorizing...   ← Thread 8
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] Up to 8 individual file lines displayed simultaneously
- [ ] Each file line updates independently in real-time
- [ ] Elapsed time increments for each file being processed
- [ ] File lines appear immediately when threads start processing
- [ ] File lines update without interfering with each other
- [ ] Number of displayed file lines matches active thread count
- [ ] Completed files show "complete" status immediately
- [ ] New files appear as threads pick up additional work
- [ ] Display handles dynamic file line changes smoothly
- [ ] Thread utilization clearly visible through active file count

## Testing Requirements

### Unit Tests Required:
- Concurrent file progress tracking
- Thread-safe display updates
- Independent file line updates
- Active thread count accuracy

### Integration Tests Required:
- Real-time updates with 8 concurrent worker threads
- Dynamic file line management during processing
- Thread utilization visibility verification