# Story: Async Display Worker

## 📖 User Story

As a **developer**, I want **a dedicated async display worker that processes state changes without blocking file processing workers** so that **I can see real-time file state updates with complete progress information on every state change**.

## ✅ Acceptance Criteria

### Given async display worker implementation

#### Scenario: Dedicated Display Worker Thread Creation
- [ ] **Given** AsyncDisplayWorker class implementation
- [ ] **When** initialized with file_tracker, progress_callback, thread_count, and total_files
- [ ] **Then** creates dedicated daemon thread for display processing
- [ ] **And** initializes bounded queue for state change events
- [ ] **And** provides start() and stop() methods for lifecycle management
- [ ] **And** worker thread name is "AsyncDisplayWorker" for debugging

#### Scenario: Queue-Based Event Processing  
- [ ] **Given** AsyncDisplayWorker running with event queue
- [ ] **When** processing state change events from queue
- [ ] **Then** pulls complete state from ConsolidatedFileTracker
- [ ] **And** calculates real progress metrics from actual file states
- [ ] **And** constructs complete progress_callback with all data
- [ ] **And** triggers CLI display update immediately

#### Scenario: Non-Blocking State Change Triggering
- [ ] **Given** worker threads triggering state changes
- [ ] **When** trigger_state_change() is called from multiple workers simultaneously
- [ ] **Then** events are queued with queue.put_nowait() (non-blocking)
- [ ] **And** method returns immediately without waiting
- [ ] **And** no worker thread blocking or performance impact
- [ ] **And** state change events include thread_id, status, and timestamp

#### Scenario: Real Progress Calculation from Central State
- [ ] **Given** complete file state data from ConsolidatedFileTracker
- [ ] **When** calculating progress metrics for display
- [ ] **Then** counts completed files from actual file states
- [ ] **And** calculates accurate progress percentage from real counts
- [ ] **And** determines active thread count from concurrent files
- [ ] **And** includes complete concurrent_files data for all workers

#### Scenario: Overflow Protection with Queue Management
- [ ] **Given** high-frequency state changes exceeding queue capacity
- [ ] **When** queue reaches maximum size (100 events)
- [ ] **Then** new events are dropped gracefully with put_nowait()
- [ ] **And** no blocking or memory growth occurs
- [ ] **And** display continues with periodic updates
- [ ] **And** system remains stable under high event load

### Pseudocode Algorithm

```
Class AsyncDisplayWorker:
    Initialize(file_tracker, progress_callback, thread_count, total_files):
        self.file_tracker = file_tracker
        self.progress_callback = progress_callback
        self.thread_count = thread_count
        self.total_files = total_files
        self.display_queue = Queue(maxsize=100)
        self.stop_event = Event()
        
    start():
        self.display_thread = Thread(target=self._worker_loop, daemon=True)
        self.display_thread.start()
        
    trigger_state_change(thread_id, status):
        Try:
            event = StateChangeEvent(thread_id, status, timestamp=now())
            self.display_queue.put_nowait(event)  // Non-blocking
        Catch QueueFull:
            Pass  // Drop event gracefully
            
    _worker_loop():
        While not self.stop_event.is_set():
            Try:
                event = self.display_queue.get(timeout=0.5)
                self._process_state_change_event(event)
            Catch QueueEmpty:
                self._trigger_periodic_update()  // Heartbeat
                
    _process_state_change_event(event):
        // Pull complete state from central store
        concurrent_files = self.file_tracker.get_concurrent_files_data()
        
        // Calculate real progress
        completed_files = count_completed_files(concurrent_files)
        progress_pct = (completed_files / self.total_files) * 100
        
        // Trigger complete progress callback
        self.progress_callback(
            current=completed_files,
            total=self.total_files,
            path=Path(""),
            info=f"{completed_files}/{self.total_files} files ({progress_pct:.0f}%) | {self.thread_count} threads",
            concurrent_files=concurrent_files
        )
```

## 🧪 Testing Requirements

### Unit Tests
- [ ] Test AsyncDisplayWorker initialization and thread management
- [ ] Test non-blocking state change event queuing
- [ ] Test queue overflow protection and event dropping
- [ ] Test complete progress calculation from ConsolidatedFileTracker data
- [ ] Test worker thread lifecycle and graceful shutdown

### Integration Tests
- [ ] Test integration with FileChunkingManager state change triggers
- [ ] Test progress_callback invocation with complete data
- [ ] Test real-time display updates with actual file processing
- [ ] Test concurrent state change handling from multiple workers
- [ ] Test overflow scenarios with high-frequency state changes

### Performance Tests
- [ ] Test event queuing latency (< 1ms for trigger_state_change)
- [ ] Test display update frequency and responsiveness
- [ ] Test memory usage with bounded queue under load
- [ ] Test CPU overhead of dedicated display worker thread
- [ ] Test worker thread performance with non-blocking state changes

### E2E Tests
- [ ] Test complete workflow: state change → queue → calculation → display
- [ ] Test real-time state visibility with actual file processing
- [ ] Test display consistency with concurrent worker state changes
- [ ] Test system behavior under various load conditions

## 🔗 Dependencies

- **ConsolidatedFileTracker**: Central state store for reading complete file status
- **FileChunkingManager**: Integration point for state change triggers  
- **CLI Progress Callback**: Existing display system for progress updates
- **Python Queue**: Thread-safe communication between workers and display
- **Threading**: Dedicated display worker thread management