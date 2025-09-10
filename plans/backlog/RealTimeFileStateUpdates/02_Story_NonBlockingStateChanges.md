# Story: Non-Blocking State Changes

## 📖 User Story

As a **file processing worker**, I want **to trigger display updates without any blocking or performance impact** so that **file processing performance remains optimal while providing real-time state visibility**.

## ✅ Acceptance Criteria

### Given non-blocking state change implementation

#### Scenario: Immediate Return from State Change Triggers
- [ ] **Given** worker thread calling _update_file_status() 
- [ ] **When** state change is triggered for display update
- [ ] **Then** method returns within 1ms (non-blocking)
- [ ] **And** no locks acquired during state change trigger
- [ ] **And** no synchronous callback execution from worker thread
- [ ] **And** file processing performance unaffected by display updates

#### Scenario: Queue-Based Event Communication
- [ ] **Given** state change trigger from worker thread
- [ ] **When** triggering display update for state change
- [ ] **Then** lightweight StateChangeEvent queued with put_nowait()
- [ ] **And** event contains thread_id, status, and timestamp only
- [ ] **And** queue operation completes immediately (< 1ms)
- [ ] **And** worker thread continues processing without delay

#### Scenario: Remove Synchronous Progress Calculations
- [ ] **Given** existing synchronous callback implementation in _update_file_status()
- [ ] **When** replacing with async queue-based approach
- [ ] **Then** all progress calculations removed from worker thread context
- [ ] **And** no calls to _calculate_files_per_second() from workers
- [ ] **And** no calls to _calculate_kbs_throughput() from workers  
- [ ] **And** no shared state locking during state changes

#### Scenario: State Change Event Queuing
- [ ] **Given** AsyncDisplayWorker with bounded event queue
- [ ] **When** multiple workers trigger state changes simultaneously
- [ ] **Then** all events queued concurrently without blocking
- [ ] **And** queue.put_nowait() used for immediate return
- [ ] **And** events processed asynchronously in display worker thread
- [ ] **And** worker threads never wait for display processing

#### Scenario: Graceful Overflow Handling
- [ ] **Given** queue at maximum capacity (100 events)
- [ ] **When** additional state change events triggered
- [ ] **Then** queue.Full exception handled gracefully
- [ ] **And** events dropped silently without blocking worker
- [ ] **And** next successful queue operation triggers display refresh
- [ ] **And** system remains stable under high event frequency

### Pseudocode Algorithm

```
Method trigger_state_change_nonblocking(thread_id, status):
    Try:
        // Create lightweight event
        event = StateChangeEvent(
            thread_id=thread_id,
            status=status,
            timestamp=time.now()
        )
        
        // Queue immediately (non-blocking)
        self.async_display_worker.queue.put_nowait(event)
        
        // Return immediately - no waiting, no calculations
        Return  // < 1ms execution time
        
    Catch QueueFull:
        // Drop event gracefully - overflow protection
        Pass
        Return  // Still immediate return
        
Method _update_file_status_with_async_trigger(thread_id, status):
    // Update central state store
    self.file_tracker.update_file_status(thread_id, status)
    
    // Async display trigger (immediate return)
    self.trigger_state_change_nonblocking(thread_id, status)
    
    // No progress calculations here - moved to display worker
    // No locks, no blocking, no synchronous operations
```

## 🧪 Testing Requirements

### Performance Tests
- [ ] Test state change trigger latency (< 1ms requirement)
- [ ] Test worker thread performance with state change triggers
- [ ] Test concurrent state change handling from 14 workers
- [ ] Test queue operation timing under various loads
- [ ] Test memory usage with bounded event queue

### Concurrency Tests  
- [ ] Test simultaneous state changes from multiple worker threads
- [ ] Test queue overflow scenarios with graceful degradation
- [ ] Test event ordering and processing under high concurrency
- [ ] Test worker thread isolation from display processing
- [ ] Test no blocking or synchronization between workers

### Integration Tests
- [ ] Test integration with existing FileChunkingManager._update_file_status()
- [ ] Test replacement of synchronous callback approach
- [ ] Test AsyncDisplayWorker receives and processes events correctly
- [ ] Test complete removal of blocking operations from worker context

### Regression Tests
- [ ] Test file processing performance maintained with async triggers
- [ ] Test existing parallel processing functionality unchanged
- [ ] Test ConsolidatedFileTracker integration preserved
- [ ] Test no deadlocks or race conditions introduced

## 🔗 Dependencies

- **AsyncDisplayWorker**: Recipient of queued state change events
- **StateChangeEvent**: Lightweight event data structure
- **ConsolidatedFileTracker**: Target for state updates (unchanged)
- **Queue Module**: Python threading.Queue for async communication
- **FileChunkingManager**: Integration point for non-blocking triggers