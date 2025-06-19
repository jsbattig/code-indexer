# Testing Safety Guide

## Production Safety Measures

The dual-engine tests in this repository are designed to avoid conflicts with production container setups. Here are the safety measures implemented:

### 1. Test-Specific Container Names

**Production containers**: `code-indexer-ollama`, `code-indexer-qdrant`
**Test containers**: `code-indexer-test-ollama-docker`, `code-indexer-test-qdrant-podman`, etc.

Test containers include:
- `test` identifier to clearly mark them as test containers
- Engine suffix (`docker`/`podman`) for isolation
- Completely different naming scheme from production

### 2. Dynamic Port Allocation

**Production ports**: 11434 (Ollama), 6333 (Qdrant)
**Test ports**: 50000+ (dynamically allocated high ports)

Test ports are:
- Randomly allocated in high ranges (50000-53999)
- Time-based to avoid conflicts between test runs
- Completely separate from standard code-indexer ports

### 3. Test-Specific Networks

**Production network**: `code-indexer-global`
**Test networks**: `code-indexer-test-global-docker`, `code-indexer-test-global-podman`

### 4. Environment Variable Protection

Tests only activate dual-engine mode when `CODE_INDEXER_DUAL_ENGINE_TEST_MODE=true` is set, ensuring production code is never affected.

## How to Run Tests Safely

### Running Individual Tests
```bash
# This automatically sets the test mode
python -m pytest tests/test_end_to_end_dual_engine.py -v
```

### Manual Cleanup (if needed)
```bash
# Stop any test containers
docker stop $(docker ps -q --filter "name=code-indexer-test-")
podman stop $(podman ps -q --filter "name=code-indexer-test-")

# Remove any test containers  
docker rm $(docker ps -aq --filter "name=code-indexer-test-")
podman rm $(podman ps -aq --filter "name=code-indexer-test-")

# Remove test networks
docker network rm code-indexer-test-global-docker
podman network rm code-indexer-test-global-podman
```

## Verification Commands

### Check for Production Conflicts
```bash
# These should NOT show any test containers
docker ps --filter "name=code-indexer-ollama"
docker ps --filter "name=code-indexer-qdrant"

# These are OK (test containers)
docker ps --filter "name=code-indexer-test-"
```

### Check Port Usage
```bash
# Check if production ports are free
ss -tlnp | grep :11434
ss -tlnp | grep :6333

# Check test port usage (should be high port numbers)
ss -tlnp | grep :5[0-3][0-9][0-9][0-9]
```

## Production Safety Checklist

✅ Test containers use completely different names  
✅ Test containers use high, randomized port numbers  
✅ Test networks are isolated and clearly named  
✅ Tests only run in explicit test mode  
✅ Automatic cleanup removes all test resources  
✅ No modification of production container registries  
✅ No interference with production data directories  

## Emergency Procedures

If you suspect test containers are interfering with production:

1. **Stop all test containers immediately**:
   ```bash
   docker stop $(docker ps -q --filter "name=code-indexer-test-")
   podman stop $(podman ps -q --filter "name=code-indexer-test-")
   ```

2. **Check for naming conflicts**:
   ```bash
   docker ps -a --filter "name=code-indexer"
   podman ps -a --filter "name=code-indexer"
   ```

3. **Remove only test containers** (be very careful with naming):
   ```bash
   # Only remove containers with "test" in the name
   docker rm $(docker ps -aq --filter "name=code-indexer-test-")
   podman rm $(podman ps -aq --filter "name=code-indexer-test-")
   ```

## Contact

If you encounter any production conflicts or safety concerns, please file an issue with:
- Container listing: `docker ps -a && podman ps -a`
- Port usage: `ss -tlnp | grep :1143[4-5] && ss -tlnp | grep :633[3-4]`
- Network listing: `docker network ls && podman network ls`