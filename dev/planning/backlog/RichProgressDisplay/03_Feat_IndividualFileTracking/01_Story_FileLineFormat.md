# Story 1: File Line Format

## User Story

**As a developer monitoring individual file processing**, I want each file to display with filename, file size, and elapsed processing time in a clear format, so that I can understand per-file processing performance and identify potential bottlenecks.

## Acceptance Criteria

### Given a file is being processed by a worker thread
### When the file progress line is displayed
### Then I should see the filename clearly identified
### And file size should be shown in human-readable format (KB)
### And elapsed processing time should be shown in seconds
### And the format should be: `├─ filename (size, elapsed) status`
### And the tree prefix (├─) should provide visual hierarchy
### And the elapsed time should update in real-time during processing

## Technical Requirements

### Pseudocode Implementation
```
FileLineManager:
    format_file_line(filename, file_size_bytes, elapsed_seconds, status):
        human_size = format_bytes_to_kb(file_size_bytes)
        elapsed_display = format_seconds(elapsed_seconds)
        return f"├─ {filename} ({human_size} KB, {elapsed_display}s) {status}"
    
    format_bytes_to_kb(bytes_count):
        kb_size = bytes_count / 1024
        return f"{kb_size:.1f}"
    
    format_seconds(elapsed):
        return f"{elapsed:.0f}"
    
    create_processing_line(file_path, start_time):
        filename = file_path.name
        file_size = get_file_size(file_path)
        elapsed = current_time - start_time
        return format_file_line(filename, file_size, elapsed, "vectorizing...")
```

### Visual Examples
```
├─ utils.py (2.1 KB, 5s) vectorizing...
├─ config.py (1.8 KB, 3s) complete
├─ main.py (3.4 KB, 7s) vectorizing...
├─ auth.py (1.2 KB, 2s) vectorizing...
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] Filename clearly identified in each file line
- [ ] File size displayed in readable KB format (e.g., "2.1 KB")
- [ ] Elapsed time shown in seconds format (e.g., "5s")
- [ ] Format follows: `├─ filename (size, elapsed) status`
- [ ] Tree prefix (├─) provides clear visual hierarchy
- [ ] Elapsed time updates in real-time during processing
- [ ] File size calculation is accurate
- [ ] Display format is consistent across all file lines

## Testing Requirements

### Unit Tests Required:
- File line formatting accuracy
- File size calculation and KB conversion
- Elapsed time calculation and display
- Format string consistency

### Integration Tests Required:
- Real-time elapsed time updates during processing
- File line display with actual file processing
- Visual hierarchy and formatting in multi-file context