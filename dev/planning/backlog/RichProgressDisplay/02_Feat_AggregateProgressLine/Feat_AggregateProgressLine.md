# Feature 2: Aggregate Progress Line

## Feature Overview

Create clean aggregate progress line showing overall progress bar, timing, file count, and performance metrics without individual file details.

## Technical Architecture

### Component Design
- **Progress Bar**: Visual progress indicator (Rich Progress component)
- **Timing Display**: Elapsed and remaining time columns
- **Metrics Line**: Files/s, KB/s, thread count on separate line
- **File Counter**: Simple X/Y files format

### Progress Format
```
Line 1: Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 37% • 0:01:23 • 0:02:12 • 45/120 files
Line 2: 12.3 files/s | 456.7 KB/s | 8 threads
```

## User Stories (Implementation Order)

### Story Implementation Checklist:
- [ ] 01_Story_CleanProgressBar
- [ ] 02_Story_AggregateMetricsLine
- [ ] 03_Story_TimingDisplay

## Dependencies
- **Prerequisites**: 01_Feat_BottomAnchoredDisplay (Rich Live foundation)
- **Dependent Features**: Individual file tracking builds on this

## Definition of Done
- [ ] Progress bar shows overall percentage completion
- [ ] Timing shows elapsed and remaining time
- [ ] Metrics line shows files/s, KB/s, active thread count
- [ ] File count shows X/Y files format
- [ ] No individual file names in aggregate line
- [ ] Clean, professional appearance