# Story 0: Atomic File Operations Infrastructure

## User Story
**As a** system administrator
**I want** all file write operations to use atomic temp-file-rename patterns
**So that** crashes during file writes never corrupt data files, ensuring zero data loss

## Business Value
Prevents catastrophic data corruption happening TODAY. Every non-atomic file write is a potential corruption point when crashes occur during I/O. This is the foundation that makes all other crash resilience features safe. Without this, implementing queue persistence, lock files, or callback queues would just create more corruption vectors.

## Current State Analysis

**CURRENT BEHAVIOR**:
- `JobPersistenceService.SaveJobAsync()` uses direct `File.WriteAllTextAsync()`
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobPersistenceService.cs` line 60
  - Risk: Crash during write = corrupted `.job.json` file
- `ResourceStatisticsService.SaveAsync()` uses direct file writes
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs` lines 147-155
  - Risk: Crash during write = corrupted statistics file
- `RepositoryRegistrationService.SaveRepositoriesAsync()` uses direct file writes
  - Location: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryRegistrationService.cs`
  - Risk: Crash during write = corrupted repository registry

**CRASH IMPACT**:
- Job metadata corrupted = job unrecoverable, workspace lost
- Statistics corrupted = capacity planning broken, requires manual file deletion
- Repository registry corrupted = all repositories inaccessible, manual intervention required

**IMPLEMENTATION REQUIRED**:
- **CREATE** `AtomicFileWriter` utility class - NEW CLASS
- **RETROFIT** all file write operations across 3 core services
- **MODIFY** ~15-20 file write locations
- **TEST** crash scenarios with partial writes

**FILES AFFECTED**:
1. `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobPersistenceService.cs`
2. `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs`
3. `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryRegistrationService.cs`
4. `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ContextLifecycleManager.cs` (session file transfers)

**EFFORT**: 3-4 days (CRITICAL - blocks all other stories, must be perfect)

## Technical Approach
Implement a shared `AtomicFileWriter` utility that enforces temp-file-rename pattern for all file operations. Retrofit all existing direct file writes to use this utility. Ensure crash during write leaves either complete old file or complete new file (never partial/corrupted).

### Components
- `AtomicFileWriter`: Shared utility for atomic write operations
- `AtomicFileReader`: Handles temp file cleanup on read operations
- Integration with existing services (JobPersistence, Statistics, Repository)

## Atomic Write Pattern Specification

### Core Pattern: Write-Temp-Rename

**Algorithm**:
```csharp
async Task WriteAtomicallyAsync(string targetPath, string content)
{
    // Step 1: Create temp file with unique suffix
    var tempPath = $"{targetPath}.tmp.{Guid.NewGuid()}";

    // Step 2: Write complete content to temp file
    await File.WriteAllTextAsync(tempPath, content, Encoding.UTF8);

    // Step 3: Flush to disk (ensure data physically written)
    using (var stream = File.OpenWrite(tempPath))
    {
        await stream.FlushAsync();
    }

    // Step 4: Atomic rename (filesystem operation is atomic)
    File.Move(tempPath, targetPath, overwrite: true);

    // Result: targetPath contains either old complete file or new complete file
    // NEVER partial/corrupted file
}
```

### Why This Works

**Crash Scenarios**:
1. **Crash before write starts**: Original file intact ✅
2. **Crash during temp file write**: Original file intact, temp file partial (ignored) ✅
3. **Crash during flush**: Original file intact, temp file may be partial (ignored) ✅
4. **Crash during rename**: Filesystem guarantees atomicity, one or the other ✅
5. **Crash after rename**: New file complete ✅

**Key Properties**:
- `File.Move()` with `overwrite: true` is atomic on Linux (rename syscall)
- Temp file uses unique GUID to prevent conflicts
- Orphaned temp files cleaned up on next startup
- Zero chance of partial file writes visible to readers

## Acceptance Criteria

```gherkin
# ========================================
# CATEGORY: AtomicFileWriter Utility Class
# ========================================

Scenario: AtomicFileWriter class creation
  Given implementing atomic file operations
  When creating shared utility
  Then AtomicFileWriter class created in /claude-batch-server/src/ClaudeBatchServer.Core/Utilities/
  And class provides WriteAtomicallyAsync(string path, string content) method
  And class provides WriteAtomicallyAsync(string path, byte[] content) method overload
  And class provides WriteAtomicallyAsync<T>(string path, T obj) method for JSON serialization
  And class is static utility (no instance state)

Scenario: Temp file naming with collision prevention
  Given atomic write operation for "/workspace/jobs/abc123/.job.json"
  When temp file is created
  Then temp file path is "/workspace/jobs/abc123/.job.json.tmp.{GUID}"
  And GUID is unique for each write operation
  And no chance of collision with concurrent writes

Scenario: Complete write-flush-rename sequence
  Given atomic write operation
  When writing content to file
  Then content written to temp file first
  And FileStream.FlushAsync() called to ensure disk write
  And File.Move(temp, target, overwrite: true) called
  And File.Move is atomic operation on Linux
  And original file replaced atomically

Scenario: Overwrite protection vs atomic guarantee
  Given target file already exists
  When atomic write operation executes
  Then File.Move called with overwrite: true
  And old file atomically replaced with new file
  And no moment where file is missing or partial

# ========================================
# CATEGORY: Temp File Cleanup on Startup
# ========================================

Scenario: Orphaned temp file detection
  Given previous crash left temp files: ".job.json.tmp.abc123"
  When system starts up
  Then all "*.tmp.*" files detected in workspace
  And cleanup service scans all directories
  And orphaned temp files deleted

Scenario: Temp file age verification before cleanup
  Given temp file ".job.json.tmp.xyz789" exists
  And temp file is older than 10 minutes
  When cleanup runs
  Then temp file is safe to delete (write must have failed)
  And file removed without data loss risk

Scenario: Concurrent write protection during cleanup
  Given temp file ".job.json.tmp.new456" exists
  And temp file is less than 10 minutes old
  When cleanup runs
  Then temp file skipped (might be active write)
  And no interference with ongoing operations

# ========================================
# CATEGORY: JobPersistenceService Retrofit
# ========================================

Scenario: SaveJobAsync atomic write integration
  Given JobPersistenceService.SaveJobAsync() method
  When modifying to use atomic writes
  Then replace File.WriteAllTextAsync() with AtomicFileWriter.WriteAtomicallyAsync()
  And location: /claude-batch-server/src/ClaudeBatchServer.Core/Services/JobPersistenceService.cs line 60
  And JSON serialization remains identical
  And error handling preserved

Scenario: Job file write crash safety
  Given job metadata being saved
  And crash occurs during write
  When system restarts
  Then job file contains complete old data OR complete new data
  And no corrupted/partial JSON
  And job can be loaded successfully

Scenario: Job file path specification
  Given job file location
  Then absolute path: /var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/.job.json
  And temp file: /var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/.job.json.tmp.{GUID}
  And paths are always absolute (no relative paths)

# ========================================
# CATEGORY: ResourceStatisticsService Retrofit
# ========================================

Scenario: Statistics SaveAsync atomic write integration
  Given ResourceStatisticsService.SaveAsync() method
  When modifying to use atomic writes
  Then replace direct file write with AtomicFileWriter.WriteAtomicallyAsync()
  And location: /claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs lines 147-155
  And existing _saveLock synchronization preserved
  And throttling behavior unchanged (2-second interval maintained)

Scenario: Statistics file crash safety
  Given statistics being saved
  And crash occurs during write
  When system restarts
  Then statistics file contains complete old data OR complete new data
  And no corrupted JSON
  And statistics can be loaded successfully

Scenario: Statistics file path specification
  Given statistics file location
  Then absolute path: /var/lib/claude-batch-server/claude-code-server-workspace/statistics.json
  And temp file: /var/lib/claude-batch-server/claude-code-server-workspace/statistics.json.tmp.{GUID}

Scenario: Concurrent statistics saves
  Given multiple job completions triggering statistics updates
  When concurrent saves attempted
  Then existing _saveLock prevents simultaneous writes
  And AtomicFileWriter prevents file corruption from race conditions
  And last save wins (latest statistics preserved)

# ========================================
# CATEGORY: RepositoryRegistrationService Retrofit
# ========================================

Scenario: SaveRepositoriesAsync atomic write integration
  Given RepositoryRegistrationService.SaveRepositoriesAsync() method
  When modifying to use atomic writes
  Then replace direct file write with AtomicFileWriter.WriteAtomicallyAsync()
  And location: /claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryRegistrationService.cs
  And repository JSON serialization unchanged

Scenario: Repository registry crash safety
  Given repository registration being saved
  And crash occurs during write
  When system restarts
  Then registry file contains complete old data OR complete new data
  And no corrupted repository list
  And all repositories remain accessible

Scenario: Repository registry file path specification
  Given repository registry location
  Then absolute path: /var/lib/claude-batch-server/claude-code-server-workspace/repositories.json
  And temp file: /var/lib/claude-batch-server/claude-code-server-workspace/repositories.json.tmp.{GUID}

# ========================================
# CATEGORY: ContextLifecycleManager Retrofit
# ========================================

Scenario: Session file transfer atomic operations
  Given ContextLifecycleManager.CompleteNewSessionAsync() transfers markdown files
  When copying session files to central repository
  Then use AtomicFileWriter for destination writes
  And location: /claude-batch-server/src/ClaudeBatchServer.Core/Services/ContextLifecycleManager.cs
  And source: /var/lib/claude-batch-server/claude-code-server-workspace/jobs/{jobId}/{sessionId}.md
  And destination: /var/lib/claude-batch-server/claude-code-server-workspace/context_repository/{sessionId}.md

Scenario: Session file crash during transfer
  Given session file being copied to central repository
  And crash occurs during copy
  When system restarts
  Then destination file is either complete or doesn't exist
  And no partial markdown files in context_repository
  And session data integrity maintained

# ========================================
# CATEGORY: Error Handling
# ========================================

Scenario: Disk full during atomic write
  Given atomic write operation
  And disk has insufficient space
  When temp file write attempted
  Then IOException thrown during write to temp file
  And original file remains intact
  And error propagated to caller
  And no partial files visible

Scenario: Permission denied during atomic write
  Given atomic write operation
  And service user lacks write permissions
  When temp file creation attempted
  Then UnauthorizedAccessException thrown
  And original file remains intact
  And error logged with full context

Scenario: Temp file cleanup failure handling
  Given orphaned temp file cannot be deleted (permission issue)
  When cleanup runs
  Then cleanup logs warning but continues
  And other temp files still cleaned up
  And system remains operational (degraded cleanup, not fatal)

# ========================================
# CATEGORY: Performance Requirements
# ========================================

Scenario: Atomic write performance overhead
  Given atomic write operation
  When compared to direct File.WriteAllTextAsync()
  Then overhead is <20% for files <1MB
  And flush operation adds <10ms
  And rename operation is <1ms (filesystem atomic operation)
  And total overhead acceptable for reliability gain

Scenario: Concurrent write throughput
  Given 10 concurrent jobs completing simultaneously
  When each triggers statistics save (atomic write)
  When each triggers job metadata save (atomic write)
  Then all writes complete successfully
  And no file corruption from race conditions
  And total time <500ms for all writes

# ========================================
# CATEGORY: Testing Requirements
# ========================================

Scenario: Crash simulation tests
  Given atomic write operation in progress
  When simulated crash via Process.Kill()
  Then target file contains complete old OR complete new data
  And no corrupted/partial files found
  And recovery is clean

Scenario: Concurrent write stress test
  Given 100 concurrent writes to same file
  When all execute simultaneously
  Then final file is valid JSON
  And no corruption detected
  And file contains data from one of the 100 writes (last writer wins)

Scenario: Orphaned temp file accumulation test
  Given 1000 crashes during writes
  When startup cleanup runs
  Then all orphaned temp files detected
  And all files older than 10 minutes deleted
  And workspace is clean
  And no disk space leak
```

## Implementation Details

### AtomicFileWriter Class Structure

**Location**: `/claude-batch-server/src/ClaudeBatchServer.Core/Utilities/AtomicFileWriter.cs`

```csharp
namespace ClaudeBatchServer.Core.Utilities;

/// <summary>
/// Provides atomic file write operations using temp-file-rename pattern.
/// Ensures crash during write never corrupts target file.
/// </summary>
public static class AtomicFileWriter
{
    /// <summary>
    /// Writes content to file atomically.
    /// </summary>
    /// <param name="targetPath">Absolute path to target file</param>
    /// <param name="content">Content to write</param>
    /// <param name="cancellationToken">Cancellation token</param>
    public static async Task WriteAtomicallyAsync(
        string targetPath,
        string content,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(targetPath);
        ArgumentNullException.ThrowIfNull(content);

        var tempPath = $"{targetPath}.tmp.{Guid.NewGuid()}";

        try
        {
            // Write to temp file
            await File.WriteAllTextAsync(tempPath, content, Encoding.UTF8, cancellationToken);

            // Ensure data is flushed to disk
            using (var stream = File.OpenWrite(tempPath))
            {
                await stream.FlushAsync(cancellationToken);
            }

            // Atomic rename (filesystem guarantees atomicity)
            File.Move(tempPath, targetPath, overwrite: true);
        }
        catch
        {
            // Clean up temp file on failure
            if (File.Exists(tempPath))
            {
                try { File.Delete(tempPath); } catch { /* Best effort */ }
            }
            throw;
        }
    }

    /// <summary>
    /// Writes object to file as JSON atomically.
    /// </summary>
    public static async Task WriteAtomicallyAsync<T>(
        string targetPath,
        T obj,
        CancellationToken cancellationToken = default)
    {
        var json = JsonSerializer.Serialize(obj, new JsonSerializerOptions
        {
            WriteIndented = true
        });
        await WriteAtomicallyAsync(targetPath, json, cancellationToken);
    }

    /// <summary>
    /// Writes byte array to file atomically.
    /// </summary>
    public static async Task WriteAtomicallyAsync(
        string targetPath,
        byte[] content,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(targetPath);
        ArgumentNullException.ThrowIfNull(content);

        var tempPath = $"{targetPath}.tmp.{Guid.NewGuid()}";

        try
        {
            await File.WriteAllBytesAsync(tempPath, content, cancellationToken);

            using (var stream = File.OpenWrite(tempPath))
            {
                await stream.FlushAsync(cancellationToken);
            }

            File.Move(tempPath, targetPath, overwrite: true);
        }
        catch
        {
            if (File.Exists(tempPath))
            {
                try { File.Delete(tempPath); } catch { /* Best effort */ }
            }
            throw;
        }
    }
}
```

### Temp File Cleanup Service

**Location**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/TempFileCleanupService.cs`

```csharp
/// <summary>
/// Cleans up orphaned temp files from crashes during atomic write operations.
/// Runs on startup to prevent disk space leaks.
/// </summary>
public class TempFileCleanupService
{
    private const int MinTempFileAgeMinutes = 10;

    public async Task CleanupOrphanedTempFilesAsync()
    {
        var workspacePath = "/var/lib/claude-batch-server/claude-code-server-workspace";
        var pattern = "*.tmp.*";

        var tempFiles = Directory.EnumerateFiles(workspacePath, pattern,
            SearchOption.AllDirectories);

        foreach (var tempFile in tempFiles)
        {
            try
            {
                var fileAge = DateTime.UtcNow - File.GetLastWriteTimeUtc(tempFile);
                if (fileAge.TotalMinutes > MinTempFileAgeMinutes)
                {
                    File.Delete(tempFile);
                    _logger.LogInformation("Cleaned up orphaned temp file: {TempFile}", tempFile);
                }
            }
            catch (Exception ex)
            {
                // Log but don't fail startup
                _logger.LogWarning(ex, "Failed to clean up temp file: {TempFile}", tempFile);
            }
        }
    }
}
```

## Integration Points

### JobPersistenceService Changes

**File**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/JobPersistenceService.cs`

**Method**: `SaveJobAsync` (line ~60)

**Change**:
```csharp
// BEFORE (Direct write - UNSAFE):
await File.WriteAllTextAsync(filePath, jsonContent);

// AFTER (Atomic write - SAFE):
await AtomicFileWriter.WriteAtomicallyAsync(filePath, jsonContent);
```

### ResourceStatisticsService Changes

**File**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ResourceMonitoring/Statistics/ResourceStatisticsService.cs`

**Method**: `SaveAsync` (lines ~147-155)

**Change**:
```csharp
// BEFORE (Direct write - UNSAFE):
await File.WriteAllTextAsync(_statisticsFilePath, json);

// AFTER (Atomic write - SAFE):
await AtomicFileWriter.WriteAtomicallyAsync(_statisticsFilePath, json);
```

### RepositoryRegistrationService Changes

**File**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/RepositoryRegistrationService.cs`

**Method**: `SaveRepositoriesAsync`

**Change**:
```csharp
// BEFORE (Direct write - UNSAFE):
await File.WriteAllTextAsync(registryPath, json);

// AFTER (Atomic write - SAFE):
await AtomicFileWriter.WriteAtomicallyAsync(registryPath, json);
```

### ContextLifecycleManager Changes

**File**: `/claude-batch-server/src/ClaudeBatchServer.Core/Services/ContextLifecycleManager.cs`

**Method**: `CompleteNewSessionAsync` (session file transfers)

**Change**:
```csharp
// BEFORE (Direct copy - UNSAFE):
File.Copy(sourcePath, destPath, overwrite: true);

// AFTER (Atomic copy - SAFE):
var content = await File.ReadAllTextAsync(sourcePath);
await AtomicFileWriter.WriteAtomicallyAsync(destPath, content);
```

## Testing Strategy

### Unit Tests
- `AtomicFileWriter.WriteAtomicallyAsync()` - basic write operations
- Temp file naming and GUID uniqueness
- Error handling (disk full, permissions, etc.)
- Concurrent write safety

### Integration Tests
- JobPersistenceService with atomic writes
- ResourceStatisticsService with atomic writes
- RepositoryRegistrationService with atomic writes
- Temp file cleanup service

### Crash Simulation Tests
- Kill process during write operation
- Verify target file is never corrupted
- Verify temp files are cleaned up on next startup
- Test 1000 simulated crashes

### Performance Tests
- Measure atomic write overhead vs direct writes
- Concurrent write throughput (100 simultaneous writes)
- Disk space usage with orphaned temp files

## Manual E2E Test Plan

### Test 1: Job Metadata Corruption Prevention
1. Create job via API
2. Kill server process during job status update
3. Restart server
4. Verify job file is valid JSON (not corrupted)
5. Verify job can be loaded and accessed

### Test 2: Statistics Corruption Prevention
1. Run 10 concurrent jobs
2. Kill server during statistics save
3. Restart server
4. Verify statistics file is valid JSON
5. Verify statistics loaded correctly

### Test 3: Temp File Cleanup
1. Simulate 50 crashes during writes (leave temp files)
2. Restart server
3. Verify all temp files older than 10 minutes deleted
4. Verify workspace is clean

## Success Criteria

- ✅ `AtomicFileWriter` utility class created and tested
- ✅ All file writes across 4 services retrofitted to use atomic operations
- ✅ Crash simulation tests pass (1000 crashes, zero corruptions)
- ✅ Temp file cleanup service runs on startup
- ✅ Performance overhead <20% for files <1MB
- ✅ All existing unit/integration tests still pass
- ✅ Zero warnings in build

## Dependencies

**Blocks**: ALL other stories (0 is foundation)
**Blocked By**: None
**Shared Components**: AtomicFileWriter used by Stories 1, 3, 4, 6, 7, 8

## Estimated Effort

**Original Estimate**: 1-2 days (OPTIMISTIC)
**Realistic Estimate**: 3-4 days

**Breakdown**:
- Day 1: Create AtomicFileWriter utility, temp file cleanup service
- Day 2: Retrofit JobPersistence, Statistics services, comprehensive testing
- Day 3: Retrofit Repository, ContextLifecycle services, crash simulation tests
- Day 4: Performance testing, edge case handling, code review fixes

**Risk**: This must be PERFECT. Bugs in atomic operations cause data loss.
