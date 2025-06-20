# Port Allocation Guide

## Production Ports (code-indexer start)

When users run `code-indexer start` in production, the following **fixed ports** are used:

### Standard Production Ports
- **Ollama**: `11434` 
- **Qdrant**: `6333`

These ports are:
- ✅ **Consistent** across all production installations
- ✅ **Documented** in official configuration
- ✅ **Expected** by users and documentation
- ⚠️  **Fixed** - same ports every time

## Test Ports (dual-engine tests)

When running the dual-engine tests (`tests/test_end_to_end_dual_engine.py`), **dynamic high ports** are used:

### Test Port Ranges
- **Podman Ollama**: `52000 + offset` (e.g., 52123)
- **Podman Qdrant**: `53000 + offset` (e.g., 53123)
- **Docker Ollama**: `50000 + offset` (e.g., 50123)
- **Docker Qdrant**: `51000 + offset` (e.g., 51123)

Where `offset = int(time.time()) % 1000` (0-999 based on current time)

### Test Port Characteristics
- ✅ **Dynamic** - different ports each test run
- ✅ **High range** - 50000-53999 to avoid production conflicts
- ✅ **Engine-specific** - Docker and Podman use different ranges
- ✅ **Time-randomized** - prevents conflicts between concurrent tests

## Port Allocation Summary

| Scenario | Ollama Port | Qdrant Port | Container Names |
|----------|-------------|-------------|-----------------|
| **Production Setup** | `11434` | `6333` | `code-indexer-ollama`, `code-indexer-qdrant` |
| **Test - Podman** | `52000+offset` | `53000+offset` | `code-indexer-test-ollama-podman`, `code-indexer-test-qdrant-podman` |
| **Test - Docker** | `50000+offset` | `51000+offset` | `code-indexer-test-ollama-docker`, `code-indexer-test-qdrant-docker` |

## Safety Analysis

### ✅ Production Safety
- Test ports (50000+) are **completely separate** from production ports (11434, 6333)
- **Zero risk** of test containers interfering with production services
- Test container names include `test` identifier for clear separation

### ✅ Port Conflict Prevention
- Production uses **low, standard ports** that users expect
- Tests use **high, randomized ports** that avoid conflicts
- Different test engines use **different port ranges**

### ✅ Multi-User Development
- Multiple developers can run tests simultaneously without port conflicts
- Time-based randomization prevents conflicts between test runs
- Each test run gets its own unique port set

## Examples

### Production Start Example
```bash
$ code-indexer start
# Creates containers:
# - code-indexer-ollama (localhost:11434)
# - code-indexer-qdrant (localhost:6333)
```

### Test Run Example
```bash
$ python -m pytest tests/test_end_to_end_dual_engine.py
# Creates test containers (example ports):
# - code-indexer-test-ollama-podman (localhost:52234)
# - code-indexer-test-qdrant-podman (localhost:53234)  
# - code-indexer-test-ollama-docker (localhost:50234)
# - code-indexer-test-qdrant-docker (localhost:51234)
```

## Verification Commands

### Check Production Ports
```bash
# Production services should be on standard ports
curl http://localhost:11434/api/version  # Ollama
curl http://localhost:6333/             # Qdrant
```

### Check Test Ports
```bash
# Tests use high port ranges (examples)
curl http://localhost:52234/api/version  # Test Ollama (Podman)
curl http://localhost:53234/             # Test Qdrant (Podman)
```

### Monitor Port Usage
```bash
# See all code-indexer related port usage
ss -tlnp | grep -E ":(11434|6333|5[0-3][0-9][0-9][0-9])"
```

## Configuration Files

### Production Config (example)
```json
{
  "ollama": {
    "host": "http://localhost:11434"
  },
  "qdrant": {
    "host": "http://localhost:6333"  
  }
}
```

### Test Config (example)
```json
{
  "ollama": {
    "host": "http://localhost:52234"
  },
  "qdrant": {
    "host": "http://localhost:53234"
  }
}
```