# Enhanced Cleanup with Collection Removal

This document describes the enhanced cleanup functionality that removes all Qdrant collections before shutting down containers.

## Why Clean Collections?

When containers are stopped and restarted, Qdrant persists its data in volumes. This means:
- Old collections remain after restart
- Test collections accumulate over time
- Stale data can interfere with fresh starts

By cleaning collections before shutdown, we ensure:
- Clean state on next startup
- No leftover test data
- Reduced disk usage
- Faster container startup (no need to load old collections)

## Usage

### 1. Command Line Script

```bash
# Basic cleanup with collection removal
./cleanup-with-collections.sh

# Force cleanup (skip confirmation, remove all containers)
./cleanup-with-collections.sh --force
```

### 2. Python Script (Direct Collection Cleanup)

```bash
# Interactive mode (asks for confirmation)
python cleanup-all-collections.py

# Force mode (no confirmation)
python cleanup-all-collections.py --force

# Specify project root
python cleanup-all-collections.py --project-root /path/to/project
```

### 3. Integration with DockerManager

The `docker_manager_cleanup_collections.py` file contains methods that can be integrated into the DockerManager class:

```python
# Method 1: Just clean collections
docker_manager.cleanup_collections_before_shutdown(verbose=True)

# Method 2: Enhanced cleanup with collection removal
docker_manager.cleanup_with_collection_removal(
    remove_data=True,
    clean_collections=True,
    verbose=True
)
```

## How It Works

1. **Detection Phase**
   - Loads project configuration to find Qdrant connection details
   - Checks if Qdrant is running and healthy
   - If not running, skips collection cleanup

2. **Collection Cleanup Phase**
   - Lists all collections in Qdrant
   - Shows collection count and names
   - Asks for confirmation (unless --force is used)
   - Deletes each collection
   - Reports success/failure for each

3. **Container Cleanup Phase**
   - Runs the standard test suite cleanup
   - Optionally force-removes all code-indexer containers

## Safety Features

- **Health Check**: Only attempts cleanup if Qdrant is actually running
- **Confirmation Prompt**: Asks for confirmation before deleting collections
- **Force Mode**: Use `--force` or `FORCE_CLEANUP=1` to skip confirmation
- **Error Handling**: Continues even if some collections fail to delete
- **Progress Reporting**: Shows what's being deleted in real-time

## Integration Points

### For Test Automation

Add to `full-automation.sh` before final cleanup:

```bash
# Clean collections before shutting down containers
"$SCRIPT_DIR/cleanup-with-collections.sh" --force
```

### For CI/CD

Set environment variable to skip confirmation:

```bash
export FORCE_CLEANUP=1
python cleanup-all-collections.py
```

### For Development

Use interactively when you want a fresh start:

```bash
./cleanup-with-collections.sh
```

## Benefits

1. **Clean State**: No leftover data between test runs
2. **Performance**: Faster container startup without old collections
3. **Disk Space**: Prevents accumulation of test data
4. **Reliability**: Reduces issues from stale data
5. **Flexibility**: Can be used standalone or integrated

## Notes

- Collections are stored in Qdrant's volume, so they persist across container restarts
- This cleanup is different from `clean-data` command which removes vector data for specific collections
- The cleanup happens BEFORE containers are stopped to ensure Qdrant is accessible
- If Qdrant is not running, collection cleanup is skipped (not an error)