# Feature 3: Individual File Tracking

## Feature Overview

Implement individual file progress lines showing filename, file size, elapsed processing time, and current processing state with appropriate labels.

## Technical Architecture

### Component Design
- **File Status Manager**: Tracks individual file processing states
- **Timer Management**: Per-file elapsed time tracking  
- **State Labels**: "vectorizing..." and "complete" status indicators
- **Display Lifecycle**: 3-second "complete" display before line removal

### File Line Format
```
├─ filename (size, elapsed) status_label
```

### State Transitions
1. **Start Processing**: `├─ utils.py (2.1 KB, 0s) vectorizing...`
2. **During Processing**: `├─ utils.py (2.1 KB, 5s) vectorizing...` 
3. **Just Completed**: `├─ utils.py (2.1 KB, 5s) complete`
4. **After 3 seconds**: Line disappears

## User Stories (Implementation Order)

### Story Implementation Checklist:
- [ ] 01_Story_FileLineFormat
- [ ] 02_Story_ProcessingStateLabels  
- [ ] 03_Story_CompletionBehavior
- [ ] 04_Story_FileMetadataDisplay

## Dependencies
- **Prerequisites**: 
  - 01_Feat_BottomAnchoredDisplay (Rich Live foundation)
  - 02_Feat_AggregateProgressLine (basic progress structure)
- **Dependent Features**: Multi-threaded updates uses this for concurrent file tracking

## Definition of Done
- [ ] Individual files show format: `├─ filename (size, elapsed) status`
- [ ] Files show "vectorizing..." while processing
- [ ] Completed files show "complete" for exactly 3 seconds
- [ ] File lines disappear after completion display period
- [ ] File size displayed in human-readable format (KB)
- [ ] Elapsed time updates in real-time during processing
- [ ] Tree-style prefix (├─) for visual hierarchy