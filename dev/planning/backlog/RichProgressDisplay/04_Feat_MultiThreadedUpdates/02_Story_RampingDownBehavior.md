# Story 2: Ramping Down Behavior

## User Story

**As a developer monitoring the end of indexing operations**, I want to see the gradual reduction of active file processing lines as threads complete their work and no new files remain, so that I can observe the natural completion sequence ending with a clean 100% progress bar.

## Acceptance Criteria

### Given file processing is nearing completion with fewer files remaining than thread count
### When worker threads complete files and no new files are available for processing
### Then the number of displayed file lines should gradually decrease
### And the thread count in aggregate metrics should decrease accordingly
### And completed file lines should disappear after their 3-second "complete" display
### And no new file lines should appear when no work remains

### Given only 2 files remain to process with 8 available threads
### When 6 threads have no work and 2 threads are processing the final files
### Then only 2 file lines should be displayed
### And aggregate metrics should show "2 threads" active
### And completed files should disappear leaving fewer active lines

### Given the last file completes processing
### When all worker threads finish and no files remain
### Then all file lines should disappear after their completion display timers
### And only the aggregate progress line should remain
### And progress bar should show 100% completion
### And thread count should show 0 threads

## Technical Requirements

### Pseudocode Implementation
```
RampingDownManager:
    handle_work_completion():
        remaining_files = get_remaining_file_queue()
        active_threads = get_active_thread_count()
        
        if len(remaining_files) < active_threads:
            # Entering ramping down phase
            expected_active_lines = len(remaining_files)
            cleanup_idle_thread_displays()
        
        if len(remaining_files) == 0:
            # Final completion phase
            wait_for_completion_timers()
            transition_to_final_state()
    
    wait_for_completion_timers():
        # Wait for all "complete" files to finish their 3-second display
        while any_files_in_completion_display():
            sleep(0.1)
            check_completion_timers()
    
    transition_to_final_state():
        clear_all_file_lines()
        show_final_progress_bar_only()
        display_completion_message()
```

### Ramping Down Sequence
```
Step 1: 8 threads, 8 file lines
├─ file1.py (1.2 KB, 3s) vectorizing...
├─ file2.py (2.1 KB, 4s) vectorizing...
[... 6 more lines ...]

Step 2: 4 threads, 4 file lines  
├─ file117.py (3.4 KB, 2s) vectorizing...
├─ file118.py (1.8 KB, 1s) vectorizing...
├─ file119.py (2.7 KB, 3s) vectorizing...
├─ file120.py (4.1 KB, 5s) vectorizing...

Step 3: 1 thread, 1 file line
├─ file120.py (4.1 KB, 8s) vectorizing...

Step 4: 0 threads, 0 file lines
Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] File lines gradually decrease as threads complete work
- [ ] Thread count decreases accordingly in aggregate metrics
- [ ] Completed files disappear after 3-second display period
- [ ] No new file lines appear when no work remains
- [ ] Display correctly handles fewer files than available threads
- [ ] Final state shows only progress bar at 100% completion
- [ ] Thread count shows 0 threads at completion
- [ ] Ramping down sequence is smooth and predictable

## Testing Requirements

### Unit Tests Required:
- Thread count reduction logic
- File line removal timing
- Final state transition behavior
- Work queue depletion handling

### Integration Tests Required:
- End-to-end ramping down sequence with real file processing
- Multiple concurrent completion scenarios
- Final state display validation