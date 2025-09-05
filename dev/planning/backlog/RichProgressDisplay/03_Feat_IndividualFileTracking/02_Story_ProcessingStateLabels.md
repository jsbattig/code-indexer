# Story 2: Processing State Labels

## User Story

**As a developer monitoring file processing states**, I want each file line to show clear status labels indicating whether files are currently being processed or have completed, so that I can understand the current state of each worker thread.

## Acceptance Criteria

### Given a worker thread starts processing a file
### When the file line is displayed
### Then the file should show status label "vectorizing..."
### And the status should clearly indicate active processing

### Given a worker thread completes processing a file  
### When the file processing finishes
### Then the file line should immediately update to show "complete" status
### And the "complete" status should be clearly distinguishable from "vectorizing..."
### And the status change should be immediate upon file completion

## Technical Requirements

### Pseudocode Implementation
```
FileStatusManager:
    PROCESSING_LABEL = "vectorizing..."
    COMPLETE_LABEL = "complete"
    
    get_status_label(file_state):
        if file_state == FileState.PROCESSING:
            return PROCESSING_LABEL
        elif file_state == FileState.COMPLETED:
            return COMPLETE_LABEL
        else:
            return "unknown"
    
    update_file_status(file_id, new_state):
        file_records[file_id].state = new_state
        status_label = get_status_label(new_state)
        trigger_display_update(file_id, status_label)
```

### State Transitions
```
File Start:    ├─ utils.py (2.1 KB, 0s) vectorizing...
Processing:    ├─ utils.py (2.1 KB, 5s) vectorizing...  
Just Complete: ├─ utils.py (2.1 KB, 5s) complete
```

### Label Requirements
- **"vectorizing..."**: Indicates active embedding generation
- **"complete"**: Indicates processing finished successfully
- **Clear Distinction**: Labels should be easily distinguishable
- **Immediate Updates**: Status changes reflected instantly

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] Files show "vectorizing..." status label while processing
- [ ] Files show "complete" status label immediately upon completion
- [ ] Status labels are clearly distinguishable from each other
- [ ] Status changes are immediate upon file completion
- [ ] Labels accurately reflect actual processing state
- [ ] Status updates are thread-safe for concurrent processing
- [ ] Labels follow consistent formatting and terminology

## Testing Requirements

### Unit Tests Required:
- Status label assignment for different file states
- State transition handling (processing → complete)
- Label display consistency and format
- Thread-safe status updates

### Integration Tests Required:
- Real-time status label updates during file processing
- Status accuracy across multiple concurrent files
- Label visibility and readability in multi-threaded context