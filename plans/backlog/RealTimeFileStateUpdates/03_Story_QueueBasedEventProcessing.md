# Story: Queue-Based Event Processing

## 📖 User Story

As a **system architect**, I want **queue-based async event processing for state changes** so that **display updates happen immediately without flooding or overwhelming the display system**.

## ✅ Acceptance Criteria

### Given queue-based event processing implementation

#### Scenario: Bounded Queue with Overflow Protection
- [ ] **Given** AsyncDisplayWorker with bounded event queue (100 events max)
- [ ] **When** state change events exceed queue capacity
- [ ] **Then** oldest events are dropped gracefully without blocking
- [ ] **And** queue.put_nowait() prevents worker thread blocking
- [ ] **And** display worker continues processing available events
- [ ] **And** system remains stable under high event frequency

#### Scenario: Event Processing Loop in Display Worker
- [ ] **Given** AsyncDisplayWorker running dedicated processing thread
- [ ] **When** processing queued state change events
- [ ] **Then** events retrieved with queue.get(timeout=0.5) 
- [ ] **And** each event triggers complete progress calculation
- [ ] **And** progress_callback invoked with real-time data
- [ ] **And** periodic updates triggered on queue timeout (heartbeat)

#### Scenario: State Change Event Structure
- [ ] **Given** StateChangeEvent data structure
- [ ] **When** created from worker thread state changes
- [ ] **Then** contains thread_id for file identification
- [ ] **And** contains FileStatus for current state
- [ ] **And** contains timestamp for event ordering
- [ ] **And** lightweight structure for minimal memory usage

#### Scenario: Async Display Worker Lifecycle Management
- [ ] **Given** AsyncDisplayWorker integrated with file processing
- [ ] **When** file processing starts and stops
- [ ] **Then** display worker starts before file processing begins
- [ ] **And** display worker stops after file processing completes
- [ ] **And** graceful shutdown with timeout (2 seconds max)
- [ ] **And** no hanging threads or resource leaks

#### Scenario: Queue Event Ordering and Processing
- [ ] **Given** multiple state change events in queue
- [ ] **When** display worker processes events sequentially
- [ ] **Then** events processed in FIFO order
- [ ] **And** each event triggers individual display update
- [ ] **And** no event batching or artificial delays
- [ ] **And** real-time responsiveness maintained

### Pseudocode Algorithm

```
Class StateChangeEvent:
    thread_id: int
    status: FileStatus  
    timestamp: float
    
Class AsyncDisplayWorker:
    Initialize(file_tracker, progress_callback, thread_count, total_files):
        self.file_tracker = file_tracker
        self.progress_callback = progress_callback
        self.display_queue = Queue(maxsize=100)
        self.stop_event = Event()
        
    start():
        self.display_thread = Thread(
            target=self._worker_loop,
            name="AsyncDisplayWorker", 
            daemon=True
        )
        self.display_thread.start()
        
    _worker_loop():
        While not self.stop_event.is_set():
            Try:
                // Get event or timeout for heartbeat
                event = self.display_queue.get(timeout=0.5)
                self._process_state_change_event(event)
                
            Catch QueueEmpty:
                // Periodic update for heartbeat
                self._trigger_periodic_display_update()
                
    _process_state_change_event(event):
        // Pull complete current state
        concurrent_files = self.file_tracker.get_concurrent_files_data()
        
        // Calculate real progress from actual state
        completed_files = self._count_completed_files(concurrent_files)
        progress_pct = (completed_files / self.total_files) * 100
        active_threads = len(concurrent_files)
        
        // Build complete info message
        info_msg = f"{completed_files}/{self.total_files} files ({progress_pct:.0f}%) | {active_threads} threads active"
        
        // Trigger real-time display update
        self.progress_callback(
            current=completed_files,
            total=self.total_files,
            path=Path(""),
            info=info_msg,
            concurrent_files=concurrent_files
        )
        
    queue_state_change(thread_id, status):
        Try:
            event = StateChangeEvent(thread_id, status, time.now())
            self.display_queue.put_nowait(event)
        Catch QueueFull:
            Pass  // Graceful overflow protection
```

## 🧪 Testing Requirements

### Queue Management Tests
- [ ] Test bounded queue behavior with max capacity
- [ ] Test event dropping with queue overflow
- [ ] Test queue.put_nowait() non-blocking behavior
- [ ] Test event ordering and FIFO processing
- [ ] Test queue memory usage under sustained load

### Event Processing Tests
- [ ] Test state change event creation and structure
- [ ] Test event processing loop with timeout handling
- [ ] Test periodic update generation on queue timeout
- [ ] Test complete progress calculation from event processing
- [ ] Test display worker thread lifecycle and shutdown

### Performance Tests
- [ ] Test event queuing latency (< 1ms)
- [ ] Test display update processing time
- [ ] Test queue capacity and memory efficiency  
- [ ] Test overflow protection performance impact
- [ ] Test sustained high-frequency event processing

### Integration Tests
- [ ] Test integration with ConsolidatedFileTracker state reading
- [ ] Test progress_callback invocation with complete data
- [ ] Test event processing accuracy vs actual file states
- [ ] Test display worker integration with file processing lifecycle

## 🔗 Dependencies

- **StateChangeEvent**: Lightweight event data structure
- **Python Queue**: Threading queue for async communication
- **ConsolidatedFileTracker**: Central state store for reading complete state
- **Threading**: Display worker thread and lifecycle management
- **Progress Callback**: CLI display system integration