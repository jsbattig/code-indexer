# Story 1: Clean Progress Bar

## User Story

**As a developer monitoring overall indexing progress**, I want a clean progress bar showing overall completion percentage, timing, and file count without individual file details, so that I can track aggregate progress in multi-threaded processing.

## Acceptance Criteria

### Given multi-threaded file processing is active
### When the aggregate progress line is displayed
### Then I should see overall completion percentage in a visual progress bar
### And elapsed time should show how long processing has been running
### And remaining time should estimate time to completion
### And file count should show format "X/Y files" (e.g., "45/120 files")
### And no individual filenames should appear in the aggregate line
### And the progress bar should visually fill as processing completes

## Technical Requirements

### Pseudocode Implementation
```
AggregateProgressBar:
    create_clean_progress_bar():
        components = [
            TextColumn("Indexing", justify="right"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),  # Percentage display
            "•",
            TimeElapsedColumn(),
            "•", 
            TimeRemainingColumn(),
            "•",
            TextColumn("{files_completed}/{files_total} files")
        ]
        return Progress(*components)
    
    update_aggregate_progress(completed, total):
        progress_bar.update(task_id, completed=completed)
        update file_count display
        calculate remaining_time estimate
```

### Visual Format
```
Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 37% • 0:01:23 • 0:02:12 • 45/120 files
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] Progress bar shows overall completion percentage visually
- [ ] Elapsed time displays current processing duration
- [ ] Remaining time estimates time to completion
- [ ] File count shows "X/Y files" format clearly
- [ ] No individual filenames appear in aggregate progress line
- [ ] Progress bar fills proportionally to completion percentage
- [ ] Visual design is clean and professional
- [ ] Updates smoothly during processing

## Testing Requirements

### Unit Tests Required:
- Progress bar percentage calculation accuracy
- File count display format correctness
- Timing display functionality
- Clean visual presentation verification

### Integration Tests Required:
- Aggregate progress updates during file processing
- Timing accuracy over processing duration
- Visual progress bar behavior with actual file completion