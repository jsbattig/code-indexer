# Story 5.2: Real-Time Updates

## Story Description

As a CIDX user monitoring sync progress, I need smooth, real-time progress updates that show current activity without flickering or jumping, maintaining the familiar single-line progress bar experience.

## Technical Specification

### Update Buffer Management

```pseudocode
class ProgressBuffer:
    def __init__(updateFrequency: Hz = 10):
        self.buffer = CircularBuffer(size=10)
        self.lastRender = 0
        self.renderInterval = 1000 / updateFrequency  # ms
        self.smoothing = ExponentialSmoothing(alpha=0.3)

    def addUpdate(progress: ProgressData):
        self.buffer.add(progress)

        # Throttle rendering
        if (now() - self.lastRender) >= self.renderInterval:
            smoothedProgress = self.smoothing.calculate(progress)
            renderProgress(smoothedProgress)
            self.lastRender = now()

class ExponentialSmoothing:
    def calculate(newValue: float) -> float:
        if self.lastValue is None:
            self.lastValue = newValue
            return newValue

        # Smooth transitions
        smoothed = self.alpha * newValue + (1 - self.alpha) * self.lastValue
        self.lastValue = smoothed
        return smoothed
```

### Terminal Rendering

```pseudocode
class TerminalRenderer:
    def renderProgress(progress: Progress):
        # Save cursor position
        saveCursor()

        # Move to progress line
        moveCursor(self.progressLine)

        # Clear line
        clearLine()

        # Render new progress
        line = formatProgressLine(progress)
        write(line)

        # Restore cursor
        restoreCursor()

    def formatProgressLine(progress: Progress) -> string:
        # Single line format matching CIDX standard
        bar = generateBar(progress.percent)
        rate = formatRate(progress.rate)
        eta = formatETA(progress.eta)
        file = truncateFilename(progress.currentFile)

        return f"{bar} {progress.percent}% | {rate} | {eta} | {file}"

    def generateBar(percent: int) -> string:
        filled = "▓" * (percent / 5)  # 20 char bar
        empty = "░" * ((100 - percent) / 5)
        return f"[{filled}{empty}]"
```

## Acceptance Criteria

### Update Frequency
```gherkin
Given progress updates from server
When rendering to terminal
Then updates should:
  - Render at 10Hz maximum
  - Buffer rapid updates
  - Smooth value transitions
  - Prevent flickering
  - Maintain 60 FPS capability
And feel responsive to user
```

### Smooth Transitions
```gherkin
Given progress value changes
When displaying updates
Then transitions should:
  - Use exponential smoothing
  - Prevent backward jumps
  - Interpolate large gaps
  - Animate bar movement
  - Show gradual changes
And appear fluid to user
```

### Buffer Management
```gherkin
Given high-frequency updates
When managing update buffer
Then the system should:
  - Store recent updates
  - Calculate moving averages
  - Detect rate changes
  - Throttle rendering
  - Prevent overflow
And maintain performance
```

### Display Rendering
```gherkin
Given terminal constraints
When rendering progress line
Then the display should:
  - Use single line (no scrolling)
  - Clear previous content
  - Handle terminal resize
  - Preserve cursor position
  - Support ANSI colors
And match CIDX standards
```

### Rate Calculation
```gherkin
Given progress over time
When calculating rates
Then the system should show:
  - Files per second
  - MB per second (for git)
  - Embeddings per second
  - Moving average (5 seconds)
  - Spike suppression
And provide useful metrics
```

## Completion Checklist

- [ ] Update frequency
  - [ ] 10Hz render loop
  - [ ] Update throttling
  - [ ] Timer management
  - [ ] Frame skipping
- [ ] Smooth transitions
  - [ ] Exponential smoothing
  - [ ] Value interpolation
  - [ ] Jump prevention
  - [ ] Animation logic
- [ ] Buffer management
  - [ ] Circular buffer
  - [ ] Update aggregation
  - [ ] Memory limits
  - [ ] Overflow handling
- [ ] Display rendering
  - [ ] Terminal control
  - [ ] Line clearing
  - [ ] Cursor management
  - [ ] ANSI support

## Test Scenarios

### Happy Path
1. Steady progress → Smooth bar → No flicker
2. Variable rate → Averaged display → Stable numbers
3. Fast updates → Throttled render → Smooth visual
4. Terminal resize → Adapts layout → Continues normally

### Error Cases
1. Terminal unavailable → Fallback to log → No crash
2. ANSI unsupported → Plain text → Still functional
3. Buffer overflow → Drop oldest → Continue smoothly
4. Render error → Recover next frame → No corruption

### Edge Cases
1. Instant completion → Show brief progress → Clean finish
2. No updates → Show stalled → Clear indication
3. Negative progress → Clamp to previous → No backwards
4. Huge files → Adjust rate units → Readable numbers

## Performance Requirements

- Render latency: <16ms (60 FPS)
- Update processing: <1ms
- Smoothing calculation: <0.5ms
- Terminal write: <5ms
- Memory usage: <10MB buffer

## Display Format Specifications

### Standard Progress Line
```
[▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░] 52% | 45 files/s | ETA: 1m 23s | processing: auth/login.py
```

### Git Operations
```
[▓▓▓▓▓▓░░░░░░░░░░░░░░] 32% | 2.3 MB/s | ETA: 45s | fetching: origin/main
```

### Indexing Operations
```
[▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░] 67% | 120 emb/s | ETA: 2m 10s | indexing: services/api.py
```

### Stalled Operation
```
[▓▓▓▓▓▓▓▓░░░░░░░░░░░░] 42% | 0 files/s | Stalled | waiting for response...
```

## Rate Calculation Algorithm

```pseudocode
class RateCalculator:
    def __init__(windowSize: seconds = 5):
        self.window = windowSize
        self.samples = []

    def addSample(count: int, timestamp: float):
        self.samples.append((count, timestamp))

        # Remove old samples outside window
        cutoff = timestamp - self.window
        self.samples = [s for s in self.samples if s[1] > cutoff]

    def getRate() -> float:
        if len(self.samples) < 2:
            return 0

        # Calculate rate over window
        timeDelta = self.samples[-1][1] - self.samples[0][1]
        countDelta = self.samples[-1][0] - self.samples[0][0]

        if timeDelta == 0:
            return 0

        rate = countDelta / timeDelta

        # Apply spike suppression
        if self.lastRate and rate > self.lastRate * 3:
            rate = self.lastRate * 1.5  # Limit growth

        self.lastRate = rate
        return rate
```

## Terminal Control Sequences

```python
# ANSI Escape Sequences
SAVE_CURSOR = "\033[s"
RESTORE_CURSOR = "\033[u"
CLEAR_LINE = "\033[2K"
MOVE_TO_COL = "\033[1G"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

# Colors
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
RESET = "\033[0m"
```

## Definition of Done

- [ ] Real-time updates at 10Hz maximum
- [ ] Smooth progress transitions
- [ ] Buffer management prevents overflow
- [ ] Single-line rendering works correctly
- [ ] Rate calculations accurate
- [ ] Terminal control sequences working
- [ ] Fallback for non-ANSI terminals
- [ ] Unit tests >90% coverage
- [ ] Performance benchmarks met
- [ ] No visual flickering