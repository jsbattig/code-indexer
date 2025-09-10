# Story: Real-Time Progress Calculations

## 📖 User Story

As a **user monitoring file processing**, I want **complete and accurate progress calculations on every state change** so that **I see real files/s, KB/s, percentages, and thread counts that reflect actual processing state in real-time**.

## ✅ Acceptance Criteria

### Given real-time progress calculations implementation

#### Scenario: Complete Progress Data from Central State
- [ ] **Given** AsyncDisplayWorker processing state change events
- [ ] **When** calculating progress metrics for display update
- [ ] **Then** reads complete file state from ConsolidatedFileTracker
- [ ] **And** counts completed files from actual COMPLETE status files
- [ ] **And** calculates progress percentage from real completed/total ratio
- [ ] **And** determines active thread count from concurrent files length
- [ ] **And** includes all 14 worker file states in concurrent_files

#### Scenario: Accurate Files Per Second Calculation
- [ ] **Given** file completion data from ConsolidatedFileTracker
- [ ] **When** calculating files processing rate
- [ ] **Then** uses actual completed file timestamps for rate calculation
- [ ] **And** implements rolling window calculation (30-second window)
- [ ] **And** provides smooth rate display without spikes
- [ ] **And** handles startup period gracefully (when few files completed)

#### Scenario: Real KB/s Throughput Calculation
- [ ] **Given** file size data from completed files
- [ ] **When** calculating throughput rate
- [ ] **Then** sums actual file sizes from completed files
- [ ] **And** calculates KB/s from cumulative bytes over time window
- [ ] **And** updates throughput calculation on each display refresh
- [ ] **And** provides accurate data throughput visibility

#### Scenario: Thread Utilization Reporting
- [ ] **Given** concurrent_files data from ConsolidatedFileTracker
- [ ] **When** determining active thread information for display
- [ ] **Then** counts files in active processing states (not COMPLETE)
- [ ] **And** shows actual number of busy worker threads
- [ ] **And** displays thread utilization accurately
- [ ] **And** differentiates between worker states (starting, chunking, vectorizing, etc.)

#### Scenario: Complete Progress Information Assembly
- [ ] **Given** real-time progress calculations completed
- [ ] **When** constructing progress information for display
- [ ] **Then** assembles complete info string with all metrics
- [ ] **And** format: "X/Y files (Z%) | A files/s | B KB/s | C threads"
- [ ] **And** all values reflect actual current processing state
- [ ] **And** no zeroed or fake values included in display

### Pseudocode Algorithm

```
Class RealTimeProgressCalculator:
    Initialize(file_tracker, total_files):
        self.file_tracker = file_tracker
        self.total_files = total_files
        self.rate_window = RollingWindow(seconds=30)
        
    calculate_complete_progress():
        // Pull complete current state
        concurrent_files = self.file_tracker.get_concurrent_files_data()
        
        // Count completed files from actual state
        completed_files = 0
        active_files = 0
        total_bytes = 0
        
        For file_data in concurrent_files:
            If file_data.status == COMPLETE:
                completed_files += 1
                total_bytes += file_data.file_size
            Else:
                active_files += 1
                
        // Calculate progress percentage
        progress_pct = (completed_files / self.total_files) * 100
        
        // Calculate files per second (rolling window)
        files_per_second = self.rate_window.calculate_rate(completed_files)
        
        // Calculate KB/s throughput
        kb_per_second = self._calculate_throughput_rate(total_bytes)
        
        // Assemble complete progress data
        Return ProgressData(
            completed_files=completed_files,
            total_files=self.total_files,
            progress_percent=progress_pct,
            files_per_second=files_per_second,
            kb_per_second=kb_per_second,
            active_threads=active_files,
            concurrent_files=concurrent_files
        )
        
    build_info_message(progress_data):
        Return f"{progress_data.completed_files}/{progress_data.total_files} files ({progress_data.progress_percent:.0f}%) | {progress_data.files_per_second:.1f} files/s | {progress_data.kb_per_second:.1f} KB/s | {progress_data.active_threads} threads"

Method process_state_change_with_calculations(event):
    // Calculate complete progress from central state
    progress_data = self.calculator.calculate_complete_progress()
    
    // Build complete progress callback
    info_msg = self.calculator.build_info_message(progress_data)
    
    // Trigger complete progress callback with real data
    self.progress_callback(
        current=progress_data.completed_files,
        total=progress_data.total_files,
        path=Path(""),
        info=info_msg,
        concurrent_files=progress_data.concurrent_files
    )
```

## 🧪 Testing Requirements

### Calculation Accuracy Tests
- [ ] Test completed files counting from ConsolidatedFileTracker state
- [ ] Test progress percentage calculation accuracy
- [ ] Test files per second calculation with rolling window
- [ ] Test KB/s throughput calculation with actual file sizes
- [ ] Test thread utilization reporting accuracy

### Real-Time Update Tests  
- [ ] Test calculation performance for high-frequency updates
- [ ] Test calculation accuracy during concurrent state changes
- [ ] Test progress data consistency across multiple rapid updates
- [ ] Test rolling window behavior with frequent calculations
- [ ] Test calculation results match actual processing state

### Integration Tests
- [ ] Test complete progress callback format and content
- [ ] Test integration with CLI progress display system
- [ ] Test progress information accuracy during actual file processing
- [ ] Test calculation performance impact on overall processing

### Performance Tests
- [ ] Test calculation latency for real-time responsiveness
- [ ] Test memory usage for rate calculation data structures
- [ ] Test calculation accuracy under various processing loads
- [ ] Test rolling window performance with high update frequency

## 🔗 Dependencies

- **ConsolidatedFileTracker**: Central state source for progress calculations
- **RollingWindow**: Time-based rate calculation utility
- **FileStatus Enum**: State classification for progress counting
- **Progress Callback**: CLI integration for complete progress data
- **Time Functions**: Accurate timing for rate calculations