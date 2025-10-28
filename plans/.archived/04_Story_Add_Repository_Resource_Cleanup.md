# Story: Add Repository Resource Cleanup

## User Story
As a **system administrator**, I want **proper resource cleanup during repository operations** so that **the system doesn't leak file handles, database connections, or memory**.

## Problem Context
Current repository operations don't properly clean up resources, leading to file handle exhaustion, database connection leaks, and memory growth over time. This causes system instability and requires periodic restarts.

## Acceptance Criteria

### Scenario 1: File Handle Cleanup on Normal Operation
```gherkin
Given a repository operation is in progress
  And the operation opens 50 file handles
When the operation completes successfully
Then all 50 file handles should be closed
  And system file handle count should return to baseline
  And no file lock warnings should appear in logs
```

### Scenario 2: Resource Cleanup on Error
```gherkin
Given a repository indexing operation is in progress
  And the operation has opened files, database connections, and allocated memory
When an error occurs during processing
Then all file handles should be closed in finally block
  And database connections should be returned to pool
  And temporary memory allocations should be freed
  And error should be logged with cleanup confirmation
```

### Scenario 3: Cleanup During Concurrent Operations
```gherkin
Given 5 repository operations are running concurrently
  And each operation uses database connections and file handles
When operations complete in random order
Then each operation should clean up its own resources
  And no resource conflicts should occur
  And total resource usage should return to baseline
  And connection pool should show all connections available
```

### Scenario 4: Cleanup on Process Termination
```gherkin
Given multiple repository operations are in progress
When the process receives SIGTERM signal
Then all operations should be gracefully stopped
  And all file handles should be closed
  And all database transactions should be rolled back
  And all temporary files should be deleted
  And shutdown should complete within 30 seconds
```

### Scenario 5: Memory Cleanup After Large Operations
```gherkin
Given a large repository with 10000 files is being indexed
  And memory usage increases to 2GB during processing
When the indexing operation completes
Then memory usage should decrease to within 10% of baseline
  And no memory leak warnings should be logged
  And garbage collection should run successfully
  And subsequent operations should not show increased baseline
```

## Technical Implementation Details

### Resource Management Strategy
```
class ResourceManager:
    def __init__(self):
        self.file_handles = set()
        self.db_connections = set()
        self.temp_files = set()
        self.background_tasks = set()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup_all()
        
    async def cleanup_all(self):
        """Clean up all tracked resources"""
        # Close file handles
        for handle in self.file_handles:
            try:
                handle.close()
            except Exception as e:
                logger.warning(f"Failed to close file handle: {e}")
        
        # Return database connections
        for conn in self.db_connections:
            try:
                await conn.close()
            except Exception as e:
                logger.warning(f"Failed to close connection: {e}")
        
        # Delete temporary files
        for temp_file in self.temp_files:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {e}")
        
        # Cancel background tasks
        for task in self.background_tasks:
            try:
                task.cancel()
            except Exception as e:
                logger.warning(f"Failed to cancel task: {e}")
```

### Repository Operation with Cleanup
```
async function process_repository_with_cleanup(repo_id: str):
    resource_manager = ResourceManager()
    
    try:
        async with resource_manager:
            // Track database connection
            conn = await get_db_connection()
            resource_manager.db_connections.add(conn)
            
            // Process files
            for file_path in repository_files:
                file_handle = open(file_path, 'rb')
                resource_manager.file_handles.add(file_handle)
                
                try:
                    content = file_handle.read()
                    await process_content(content)
                finally:
                    file_handle.close()
                    resource_manager.file_handles.discard(file_handle)
            
            // Commit transaction
            await conn.commit()
            
    except Exception as e:
        logger.error(f"Repository processing failed: {e}")
        raise
    finally:
        // Ensure cleanup even if context manager fails
        await resource_manager.cleanup_all()
        
        // Log resource status
        log_resource_usage()
```

### Signal Handler Implementation
```
class GracefulShutdown:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.active_operations = set()
        
    def register_operation(self, operation_id):
        self.active_operations.add(operation_id)
        
    def unregister_operation(self, operation_id):
        self.active_operations.discard(operation_id)
        
    async def shutdown(self, signal):
        logger.info(f"Received {signal}, starting graceful shutdown")
        
        // Set shutdown flag
        self.shutdown_event.set()
        
        // Cancel all active operations
        tasks = []
        for op_id in self.active_operations:
            tasks.append(cancel_operation(op_id))
        
        // Wait for cancellations with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error("Shutdown timeout, forcing termination")
        
        // Final cleanup
        await cleanup_all_resources()
        logger.info("Graceful shutdown completed")

// Register signal handlers
signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(shutdown_handler.shutdown(s)))
signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(shutdown_handler.shutdown(s)))
```

### Memory Management
```
async function monitor_memory_usage():
    import psutil
    import gc
    
    process = psutil.Process()
    baseline_memory = process.memory_info().rss
    
    async def check_memory():
        current_memory = process.memory_info().rss
        increase_mb = (current_memory - baseline_memory) / 1024 / 1024
        
        if increase_mb > 500:  // 500MB increase
            logger.warning(f"Memory usage increased by {increase_mb:.2f}MB")
            
            // Force garbage collection
            gc.collect()
            
            // Check again after GC
            new_memory = process.memory_info().rss
            if new_memory > current_memory * 0.9:
                logger.error("Possible memory leak detected")
                
                // Dump memory profile
                await dump_memory_profile()
    
    // Schedule periodic checks
    while True:
        await asyncio.sleep(60)  // Check every minute
        await check_memory()
```

## Testing Requirements

### Unit Tests
- [ ] Test ResourceManager cleanup in normal flow
- [ ] Test ResourceManager cleanup on exception
- [ ] Test file handle tracking and cleanup
- [ ] Test database connection cleanup
- [ ] Test temp file deletion

### Integration Tests
- [ ] Test resource cleanup with real files
- [ ] Test database transaction rollback
- [ ] Test concurrent operation cleanup
- [ ] Test signal handler shutdown

### Performance Tests
- [ ] Test resource usage under load
- [ ] Test memory usage patterns
- [ ] Test file handle limits
- [ ] Test connection pool exhaustion

### E2E Tests
- [ ] Test complete operation with monitoring
- [ ] Test shutdown during active operations
- [ ] Test resource recovery after errors
- [ ] Test long-running operation cleanup

## Definition of Done
- [x] All repository operations use ResourceManager
- [x] File handles properly tracked and closed
- [x] Database connections returned to pool
- [x] Memory usage returns to baseline after operations
- [x] Graceful shutdown implemented and tested
- [x] No resource leak warnings in 24-hour test
- [x] Unit test coverage > 90%
- [x] Integration tests pass
- [x] Performance tests show no degradation
- [x] Monitoring and alerting configured
- [x] Documentation updated

## Performance Criteria
- Zero file handle leaks after 1000 operations
- Memory usage stable over 24 hours
- Shutdown completes within 30 seconds
- Resource cleanup overhead < 5% of operation time
- Support 100 concurrent operations without resource exhaustion

## Monitoring Requirements
- Track file handle count over time
- Monitor database connection pool usage
- Track memory usage and growth patterns
- Log resource cleanup operations
- Alert on resource leak indicators
- Dashboard showing resource utilization