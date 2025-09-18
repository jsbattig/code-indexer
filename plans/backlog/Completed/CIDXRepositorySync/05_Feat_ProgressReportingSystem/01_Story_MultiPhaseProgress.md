# Story 5.1: Multi-Phase Progress

## Story Description

As a CIDX user watching sync progress, I need to see distinct phases of the sync operation with accurate progress for each phase, so I understand what's happening and how long each step will take.

## Technical Specification

### Phase Definition Model

```pseudocode
class SyncPhase:
    name: string
    weight: float          # Contribution to overall progress
    startPercent: int      # Starting point in overall progress
    endPercent: int        # Ending point in overall progress
    currentProgress: int   # 0-100 within this phase
    status: PENDING | ACTIVE | COMPLETED | FAILED
    startTime: timestamp
    estimatedDuration: seconds

SYNC_PHASES = [
    SyncPhase("Initializing", weight=0.05, start=0, end=5),
    SyncPhase("Git Fetch", weight=0.25, start=5, end=30),
    SyncPhase("Git Merge", weight=0.10, start=30, end=40),
    SyncPhase("Detecting Changes", weight=0.05, start=40, end=45),
    SyncPhase("Indexing Files", weight=0.45, start=45, end=90),
    SyncPhase("Validating Index", weight=0.10, start=90, end=100)
]

class PhaseManager:
    def calculateOverallProgress():
        overall = 0
        for phase in phases:
            if phase.status == COMPLETED:
                overall += phase.weight * 100
            elif phase.status == ACTIVE:
                overall += phase.weight * phase.currentProgress
        return overall

    def transitionPhase(fromPhase: Phase, toPhase: Phase):
        fromPhase.status = COMPLETED
        fromPhase.currentProgress = 100
        toPhase.status = ACTIVE
        toPhase.startTime = now()
        updateDisplay()
```

## Acceptance Criteria

### Phase Definition
```gherkin
Given sync operation phases
When defining phase structure
Then each phase should have:
  - Descriptive name
  - Weight (contribution to total)
  - Progress range (start-end %)
  - Current progress (0-100)
  - Status indicator
And weights should sum to 1.0
```

### Weight Allocation
```gherkin
Given different sync scenarios
When allocating phase weights
Then weights should reflect:
  - Git operations: 35% total
  - Change detection: 5%
  - Indexing: 45% (largest portion)
  - Validation: 10%
  - Overhead: 5%
And be adjustable based on history
```

### Phase Transitions
```gherkin
Given an active phase completes
When transitioning to next phase
Then the system should:
  - Mark current phase as COMPLETED
  - Set progress to 100%
  - Activate next phase
  - Reset phase progress to 0%
  - Update overall progress
And transition smoothly
```

### Overall Calculation
```gherkin
Given multiple phases with progress
When calculating overall progress
Then the system should:
  - Sum weighted contributions
  - Account for completed phases
  - Include partial progress
  - Ensure monotonic increase
  - Never exceed 100%
And provide accurate percentage
```

### Dynamic Adjustment
```gherkin
Given historical phase durations
When starting new sync
Then the system should:
  - Load previous timing data
  - Adjust phase weights
  - Improve time estimates
  - Learn from patterns
  - Adapt to repository size
And increase accuracy over time
```

## Completion Checklist

- [ ] Phase definition
  - [ ] Phase data structure
  - [ ] Default phase list
  - [ ] Weight configuration
  - [ ] Status tracking
- [ ] Weight allocation
  - [ ] Initial weights
  - [ ] Weight validation
  - [ ] Dynamic adjustment
  - [ ] Historical learning
- [ ] Phase transitions
  - [ ] State machine
  - [ ] Transition logic
  - [ ] Event handling
  - [ ] Progress updates
- [ ] Overall calculation
  - [ ] Weighted sum algorithm
  - [ ] Progress validation
  - [ ] Monotonic guarantee
  - [ ] Boundary checks

## Test Scenarios

### Happy Path
1. All phases complete → 100% reached → Accurate tracking
2. Skip phase → Weights redistribute → Total still 100%
3. Quick phases → Fast transitions → Smooth progress
4. Long indexing → Gradual progress → Accurate estimates

### Error Cases
1. Phase fails → Mark failed → Continue next phase
2. Weight sum ≠ 1.0 → Auto-normalize → Warning logged
3. Progress reverses → Clamp to previous → No backwards
4. Phase skipped → Redistribute weight → Maintain accuracy

### Edge Cases
1. Single file → Minimal indexing → Adjust weights
2. No changes → Skip indexing → Progress jumps
3. Huge repository → Extended phases → Weights adapt
4. Instant complete → All phases flash → Still show

## Performance Requirements

- Phase transition: <10ms
- Progress calculation: <1ms
- Weight adjustment: <5ms
- Display update: <16ms (60 FPS)
- History lookup: <10ms

## Phase Display Examples

### Active Phase Progress
```
📊 Git Fetch (25% of total sync)
   ▓▓▓▓▓▓▓░░░░░░░░░░░░░ 35% | Fetching remote changes...
   Overall: ▓▓▓▓░░░░░░░░░░░░░░░░ 18% | ETA: 2m 15s
```

### Phase Transition
```
✓ Git Fetch completed (1m 23s)
📊 Git Merge (10% of total sync)
   ░░░░░░░░░░░░░░░░░░░░ 0% | Starting merge...
   Overall: ▓▓▓▓▓▓░░░░░░░░░░░░░░ 30% | ETA: 1m 45s
```

### Multi-Phase Summary
```
Sync Progress Overview:
  ✓ Initializing     [████████████████████] 100%  (2s)
  ✓ Git Fetch        [████████████████████] 100%  (45s)
  ⚡ Git Merge        [███████░░░░░░░░░░░░░] 35%   (5s)
  ⏸ Detecting Changes [░░░░░░░░░░░░░░░░░░░░] 0%    (waiting)
  ⏸ Indexing Files   [░░░░░░░░░░░░░░░░░░░░] 0%    (waiting)
  ⏸ Validating       [░░░░░░░░░░░░░░░░░░░░] 0%    (waiting)
```

## Weight Learning Algorithm

```pseudocode
class WeightLearner:
    def updateWeights(completedSync: SyncMetrics):
        for phase in completedSync.phases:
            # Calculate actual vs expected
            actualWeight = phase.duration / completedSync.totalDuration
            expectedWeight = phase.configuredWeight

            # Apply exponential moving average
            alpha = 0.2  # Learning rate
            newWeight = alpha * actualWeight + (1 - alpha) * expectedWeight

            # Store for next sync
            phase.configuredWeight = newWeight

        # Normalize to sum to 1.0
        normalizeWeights()

    def predictPhaseDuration(phase: Phase, repoSize: int):
        baseline = getHistoricalAverage(phase.name)
        sizeFactor = log(repoSize) / log(averageRepoSize)
        return baseline * sizeFactor
```

## Definition of Done

- [ ] Phase structure defined with all fields
- [ ] Default phases configured with weights
- [ ] Phase transitions working smoothly
- [ ] Overall progress calculation accurate
- [ ] Weight learning algorithm implemented
- [ ] Display shows phase information
- [ ] Historical data persistence
- [ ] Unit tests >90% coverage
- [ ] Integration tests verify transitions
- [ ] Performance requirements met