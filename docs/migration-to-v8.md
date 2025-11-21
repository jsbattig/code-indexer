# Migration Guide: v7.x to v8.0

## Overview

Version 8.0.0 represents a major architectural simplification of code-indexer, removing legacy infrastructure and consolidating around a streamlined container-free architecture. This guide walks you through upgrading from v7.x to v8.0.

## Breaking Changes Summary

### Removed Features

#### 1. Qdrant Backend (Removed)
- The Qdrant vector database backend has been completely removed
- Only the filesystem backend is supported in v8.0+
- Container management infrastructure has been eliminated

#### 2. Container Infrastructure (Removed)
- All Docker/Podman container management code removed
- No more container orchestration, port management, or container health checks
- Code-indexer now runs entirely container-free

#### 3. Ollama Embedding Provider (Removed)
- Ollama local embeddings provider has been removed
- VoyageAI is the only supported embedding provider in v8.0+
- Focus on production-quality cloud-based embeddings

### Impact Summary

**What's Removed:**
- QdrantContainerBackend class and all integration code
- DockerManager, ContainerManager, and port registry system
- OllamaClient and local embedding infrastructure
- Container-related CLI commands and configuration options
- Approximately 15,000 lines of legacy code
- 135 deprecated test files

**What Remains:**
- FilesystemVectorStore (only backend)
- VoyageAI embeddings (only provider)
- CLI Mode and Daemon Mode (simplified)
- Server Mode (simplified, container-free)
- All core semantic search functionality

## Migration Steps

### Step 1: Backup Your Current Index

Before upgrading, backup your existing index data:

```bash
# Backup local project index
cp -r .code-indexer .code-indexer.backup

# If using server mode, backup server data
cp -r ~/.cidx-server ~/.cidx-server.backup
```

### Step 2: Upgrade Code-Indexer

```bash
# Using pipx (recommended)
pipx upgrade code-indexer

# Or using pip in virtual environment
pip install --upgrade code-indexer
```

Verify the new version:

```bash
cidx --version
# Should show: 8.0.0 or higher
```

### Step 3: Update Configuration

#### Remove Legacy Configuration Fields

Edit your `.code-indexer/config.json` and remove these fields if present:

```json
{
  "qdrant_config": { ... },           // REMOVE - No longer supported
  "ollama_config": { ... },           // REMOVE - No longer supported
  "containers_config": { ... },       // REMOVE - No longer supported
  "project_ports": { ... },           // REMOVE - No longer needed
  "project_containers": { ... }       // REMOVE - No longer needed
}
```

#### Update Backend and Provider Settings

Your configuration should now only specify:

```json
{
  "project_root": "/path/to/your/project",
  "embedding_provider": {
    "provider_type": "voyage-ai",
    "model": "voyage-3"
  },
  "vector_store": {
    "provider": "filesystem"
  }
}
```

Or simply rely on defaults (filesystem backend and VoyageAI are automatic):

```json
{
  "project_root": "/path/to/your/project"
}
```

### Step 4: Set Up VoyageAI API Key

If you were using Ollama, you now need a VoyageAI API key:

```bash
# Export API key
export VOYAGE_API_KEY="your-api-key-here"

# Or add to your shell profile
echo 'export VOYAGE_API_KEY="your-api-key-here"' >> ~/.bashrc
source ~/.bashrc
```

Get your API key from: https://www.voyageai.com/

### Step 5: Stop Legacy Services

If you were using containers with Qdrant:

```bash
# These commands are now no-ops in v8.0 but safe to run
cidx stop
```

If you had containers running manually:

```bash
# Stop Qdrant containers
podman stop cidx-qdrant-<project>
# or
docker stop cidx-qdrant-<project>

# Remove containers
podman rm cidx-qdrant-<project>
docker rm cidx-qdrant-<project>
```

### Step 6: Re-Initialize and Re-Index

Re-initialize your project with the new filesystem backend:

```bash
# Navigate to your project
cd /path/to/your/project

# Clean old data (optional but recommended)
rm -rf .code-indexer

# Initialize with v8.0 defaults
cidx init

# Re-index your codebase
cidx index
```

For projects with git history indexing:

```bash
cidx index --index-commits
```

### Step 7: Verify Migration

Test that everything works:

```bash
# Check status
cidx status

# Run a test query
cidx query "authentication logic"

# If using daemon mode
cidx config --daemon
cidx start
cidx query "test query"
```

## Before/After Configuration Examples

### Before (v7.x with Qdrant)

```json
{
  "project_root": "/home/user/myproject",
  "embedding_provider": {
    "provider_type": "voyage-ai",
    "model": "voyage-3"
  },
  "vector_store": {
    "provider": "qdrant",
    "qdrant_config": {
      "port": 6333,
      "container_name": "cidx-qdrant-myproject"
    }
  },
  "project_ports": {
    "qdrant_port": 6333,
    "qdrant_grpc_port": 6334
  },
  "project_containers": {
    "qdrant_container": "cidx-qdrant-myproject"
  }
}
```

### After (v8.0 with Filesystem)

```json
{
  "project_root": "/home/user/myproject",
  "embedding_provider": {
    "provider_type": "voyage-ai",
    "model": "voyage-3"
  },
  "vector_store": {
    "provider": "filesystem"
  }
}
```

Or even simpler (relies on defaults):

```json
{
  "project_root": "/home/user/myproject"
}
```

### Before (v7.x with Ollama)

```json
{
  "project_root": "/home/user/myproject",
  "embedding_provider": {
    "provider_type": "ollama",
    "model": "nomic-embed-text"
  },
  "vector_store": {
    "provider": "filesystem"
  }
}
```

### After (v8.0 with VoyageAI)

```json
{
  "project_root": "/home/user/myproject",
  "embedding_provider": {
    "provider_type": "voyage-ai",
    "model": "voyage-3"
  },
  "vector_store": {
    "provider": "filesystem"
  }
}
```

## Troubleshooting

### Error: "Qdrant backend is no longer supported"

**Cause**: Your configuration still references Qdrant backend.

**Solution**:
1. Remove `"qdrant_config"` from your configuration file
2. Set `"vector_store": { "provider": "filesystem" }` or remove (default is filesystem)
3. Re-index: `cidx index`

### Error: "Ollama provider is no longer supported"

**Cause**: Your configuration still references Ollama embedding provider.

**Solution**:
1. Remove `"ollama_config"` from your configuration file
2. Set `"embedding_provider": { "provider_type": "voyage-ai" }`
3. Export VoyageAI API key: `export VOYAGE_API_KEY="your-key"`
4. Re-index: `cidx index`

### Error: "Container configuration detected"

**Cause**: Your configuration contains container-related fields.

**Solution**:
1. Remove `"containers_config"`, `"project_ports"`, and `"project_containers"` from configuration
2. Code-indexer v8.0 runs container-free
3. Re-initialize if needed: `cidx init`

### Error: "VOYAGE_API_KEY not found"

**Cause**: VoyageAI API key not set in environment.

**Solution**:
```bash
export VOYAGE_API_KEY="your-api-key-here"
# Verify it's set
echo $VOYAGE_API_KEY
# Re-run command
cidx index
```

### Queries are slower after migration

**Cause**: HNSW index may need rebuilding.

**Solution**:
```bash
cidx index --rebuild-index
```

### Missing commit history after migration

**Cause**: Git commit indexing needs to be re-run.

**Solution**:
```bash
cidx index --index-commits
```

### Daemon mode not starting

**Cause**: Daemon configuration may need updating.

**Solution**:
```bash
# Check daemon status
cidx status

# Enable daemon mode
cidx config --daemon

# Start daemon
cidx start
```

## Rollback Instructions

If you need to roll back to v7.x:

### Step 1: Restore Backup

```bash
# Restore project index
rm -rf .code-indexer
mv .code-indexer.backup .code-indexer

# If using server mode
rm -rf ~/.cidx-server
mv ~/.cidx-server.backup ~/.cidx-server
```

### Step 2: Downgrade Package

```bash
# Using pipx
pipx install code-indexer==7.4.0

# Or using pip
pip install code-indexer==7.4.0
```

### Step 3: Verify Rollback

```bash
cidx --version
# Should show: 7.4.0

cidx status
cidx query "test query"
```

## Benefits of v8.0 Migration

### Performance Improvements

- **Faster startup**: No container initialization overhead
- **Reduced complexity**: Simpler architecture means fewer potential failure points
- **Cleaner codebase**: 15,000 lines of legacy code removed

### Operational Benefits

- **No container runtime required**: Works on any system with Python
- **Simpler deployment**: No Docker/Podman dependency
- **Easier troubleshooting**: Fewer components to debug
- **Lower resource usage**: No container overhead

### Development Benefits

- **Faster test suite**: ~30% improvement in test execution time
- **Reduced maintenance**: Less infrastructure to maintain
- **Clearer architecture**: Focus on core semantic search functionality

## Getting Help

### Documentation

- **README**: Updated with v8.0 usage examples
- **Architecture docs**: See `docs/architecture.md` for v8.0 architecture overview
- **CLAUDE.md**: Updated project instructions for v8.0

### Support Channels

- **GitHub Issues**: https://github.com/jsbattig/code-indexer/issues
- **Discussions**: https://github.com/jsbattig/code-indexer/discussions

### Reporting Migration Issues

When reporting migration issues, please include:

1. Previous version (e.g., v7.4.0)
2. Current version (e.g., v8.0.0)
3. Operating system and Python version
4. Relevant configuration (sanitize sensitive data)
5. Error messages or unexpected behavior
6. Steps you've taken so far

## Frequently Asked Questions

### Can I still use Qdrant if I prefer it?

No, Qdrant support has been completely removed in v8.0. The filesystem backend is now the only option. If you absolutely require Qdrant, you must stay on v7.x.

### Can I use local embeddings instead of VoyageAI?

No, Ollama local embeddings have been removed. VoyageAI is the only supported embedding provider in v8.0. VoyageAI provides production-quality embeddings with excellent performance.

### Will container support be added back in the future?

No, the decision to remove containers is permanent. Code-indexer v8.0+ focuses on a streamlined, container-free architecture.

### What if I need multi-user server mode?

Server mode is still available in v8.0, but now runs container-free using the filesystem backend. See the updated server documentation for details.

### How much does VoyageAI cost?

VoyageAI offers a free tier for development and testing. See their pricing page for production pricing: https://www.voyageai.com/pricing

### Do I need to re-index after migration?

Yes, you must re-index your codebase after migrating to v8.0. The filesystem storage format is different from Qdrant, so a fresh index is required.

### Will my old index data still work?

No, Qdrant-based indexes cannot be directly migrated. You must re-index using the filesystem backend. This typically takes minutes for medium-sized codebases.

### Can I migrate incrementally?

No, v8.0 is a major breaking release. You must fully migrate all projects and cannot run v7.x and v8.0 side-by-side on the same project.

## Migration Checklist

Use this checklist to track your migration progress:

- [ ] Backup existing index data
- [ ] Upgrade to code-indexer v8.0.0
- [ ] Remove legacy configuration fields (qdrant_config, ollama_config, containers_config)
- [ ] Set up VoyageAI API key if migrating from Ollama
- [ ] Stop and remove any Qdrant containers
- [ ] Re-initialize project: `cidx init`
- [ ] Re-index codebase: `cidx index`
- [ ] Re-index git history if needed: `cidx index --index-commits`
- [ ] Verify queries work: `cidx query "test"`
- [ ] Update CI/CD pipelines if applicable
- [ ] Update team documentation if applicable
- [ ] Remove backup after confirming everything works

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-20 | Initial migration guide for v8.0.0 release |
