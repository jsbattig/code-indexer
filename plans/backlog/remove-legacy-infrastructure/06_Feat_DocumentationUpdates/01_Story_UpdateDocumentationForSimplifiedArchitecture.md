# Story: Update Documentation for Simplified Architecture

## Story ID
`STORY-DOCS-UPDATE-001`

## Parent Feature
`FEAT-DOCS-UPDATE-001`

## Title
Update All Documentation to Reflect Simplified Architecture

## Status
PLANNED

## Priority
LOW

## Story Points
3

## Assignee
TBD

## Story Summary

As a user of code-indexer, I want the documentation to accurately reflect the simplified v8.0 architecture so that I can understand how to use the container-free filesystem backend, migrate from previous versions, and contribute to the project without confusion about deprecated features.

## Acceptance Criteria

### Required Outcomes
1. **README.md Updates**
   - [ ] Remove all Qdrant backend mentions
   - [ ] Remove all container/Docker/Podman references
   - [ ] Remove Ollama provider mentions
   - [ ] Update installation instructions for v8.0
   - [ ] Simplify configuration examples
   - [ ] Update usage examples with current CLI

2. **CLAUDE.md Updates**
   - [ ] Remove Mode 3 container concepts
   - [ ] Remove Qdrant backend sections
   - [ ] Remove Ollama provider sections
   - [ ] Update architecture overview
   - [ ] Simplify configuration instructions
   - [ ] Update version references to v8.0

3. **Migration Guide Creation**
   - [ ] Create docs/migration/migration-to-v8.md
   - [ ] List all breaking changes
   - [ ] Provide step-by-step migration instructions
   - [ ] Include before/after configuration examples
   - [ ] Add troubleshooting section
   - [ ] Include rollback instructions

4. **Architecture Documentation**
   - [ ] Create docs/architecture/v8.0.0-simplified.md
   - [ ] Document filesystem-only backend
   - [ ] Document VoyageAI-only embeddings
   - [ ] Remove container architecture sections
   - [ ] Update component diagrams

5. **CHANGELOG Entry**
   - [ ] Add v8.0.0 section with breaking changes
   - [ ] List all removed features
   - [ ] Highlight migration requirements
   - [ ] Note performance improvements

6. **Example Updates**
   - [ ] Update all configuration file examples
   - [ ] Update all CLI command examples
   - [ ] Test all code snippets work
   - [ ] Verify all links are valid

## Technical Details

### Implementation Steps

1. **README.md Updates** (2 hours)
   ```markdown
   # Remove sections like:
   - Container Management
   - Qdrant Backend
   - Ollama Integration

   # Update installation to:
   ## Installation
   Code-indexer requires Python 3.9+ and runs container-free.

   ```bash
   pip install code-indexer
   export VOYAGE_API_KEY=your-api-key
   cidx init
   cidx index
   cidx query "your search"
   ```

   # Simplify configuration:
   ## Configuration
   Code-indexer uses a simple filesystem backend with VoyageAI embeddings.

   ```yaml
   project_root: .
   backend_type: filesystem  # Only option in v8.0+
   embedding_provider: voyageai  # Only option in v8.0+
   ```
   ```

2. **CLAUDE.md Updates** (1 hour)
   ```markdown
   # Update Operational Modes:
   ## Operational Modes Overview
   CIDX has **two operational modes** (simplified from three in v7):

   ### Mode 1: CLI Mode (Direct, Local)
   - Direct command-line tool
   - FilesystemVectorStore backend
   - No containers, instant setup

   ### Mode 2: Daemon Mode (Local, Cached)
   - Background service for faster queries
   - Unix socket communication
   - No containers, runs as local process

   # Remove all sections mentioning:
   - Qdrant
   - Containers
   - Ollama
   ```

3. **Create Migration Guide** (2 hours)
   ```markdown
   # Migration Guide: v7.x to v8.0

   ## Breaking Changes

   ### Removed Features
   1. **Qdrant Backend** - No longer supported
   2. **Container Management** - Completely removed
   3. **Ollama Embeddings** - Removed, use VoyageAI

   ## Migration Steps

   ### 1. Backup Current Index
   ```bash
   cp -r .code-indexer .code-indexer.backup
   ```

   ### 2. Update Configuration
   Remove from your config:
   - `qdrant_config`
   - `ollama_config`
   - `containers_config`

   ### 3. Re-index Your Codebase
   ```bash
   cidx index --force
   ```

   ## Troubleshooting

   ### Error: "Qdrant backend is no longer supported"
   Solution: Remove `backend_type: qdrant` from config

   ### Error: "Ollama provider is no longer supported"
   Solution: Set up VoyageAI API key and re-index
   ```

4. **Architecture Documentation** (1 hour)
   ```markdown
   # Code-Indexer v8.0 Architecture

   ## Overview
   Simplified, container-free architecture focusing on:
   - FilesystemVectorStore (only backend)
   - VoyageAI embeddings (only provider)
   - Local daemon mode (no containers)

   ## Components

   ### Vector Storage
   - Filesystem-based storage in `.code-indexer/index/`
   - No external dependencies
   - Git-aware deduplication

   ### Embedding Generation
   - VoyageAI API integration only
   - Batch processing with 120k token limit
   - Automatic retry logic

   ## Removed Components
   - QdrantContainerBackend
   - DockerManager/ContainerManager
   - OllamaClient
   - Port registry management
   ```

5. **CHANGELOG Entry** (30 min)
   ```markdown
   ## [8.0.0] - 2025-01-XX

   ### BREAKING CHANGES
   - Removed Qdrant backend support - use filesystem backend
   - Removed container management - runs container-free
   - Removed Ollama embedding provider - use VoyageAI only
   - Simplified configuration schema
   - Users must re-index after upgrade

   ### Removed
   - QdrantContainerBackend class and integration
   - DockerManager and ContainerManager infrastructure
   - OllamaClient embedding provider
   - Container-related CLI commands
   - ~15,000 lines of legacy code
   - ~135 deprecated test files

   ### Improved
   - Test suite runs ~30% faster
   - Simpler installation without container runtime
   - Cleaner configuration with fewer options
   - Reduced maintenance burden

   ### Migration
   See [Migration Guide](docs/migration/migration-to-v8.md)
   ```

6. **Test Documentation** (30 min)
   ```bash
   # Test all examples in documentation
   for example in $(grep -h "```bash" README.md | ...); do
       eval "$example"
   done

   # Verify all links
   markdown-link-check README.md
   markdown-link-check CLAUDE.md
   markdown-link-check docs/**/*.md
   ```

### Files to Modify

**Primary Updates:**
- README.md
- CLAUDE.md
- CHANGELOG.md

**New Files:**
- docs/migration/migration-to-v8.md
- docs/architecture/v8.0.0-simplified.md

**Secondary Updates:**
- docs/installation.md
- docs/configuration.md
- docs/examples/*.md

### Documentation Standards

Follow NO EMOJI rule from CLAUDE.md:
```markdown
# CORRECT: Plain text headers
### Performance Improvements
### Configuration Updates

# INCORRECT: No emoji/icons
### 🚀 Performance Improvements
### ⚙️ Configuration Updates
```

## Test Requirements

### Documentation Validation
1. All code examples must execute successfully
2. All configuration examples must be valid
3. All links must resolve correctly
4. Migration guide must be tested step-by-step

### Review Checklist
1. [ ] Technical accuracy verified
2. [ ] No legacy feature references remain
3. [ ] Examples tested and working
4. [ ] Links validated
5. [ ] Migration guide walkthrough completed
6. [ ] Spelling and grammar checked

### Manual Testing Checklist
1. [ ] Follow installation instructions - works
2. [ ] Follow migration guide - successful upgrade
3. [ ] Try all CLI examples - all work
4. [ ] Check all configuration examples - valid
5. [ ] Test troubleshooting steps - helpful
6. [ ] Verify no broken links
7. [ ] Confirm no emoji in documentation

## Dependencies

### Blocked By
- All code changes (Features 1-5)
- Must have final CLI interface
- Must have final configuration schema

### Blocks
- v8.0.0 release

## Definition of Done

1. [ ] README.md updated with no legacy references
2. [ ] CLAUDE.md updated for v8.0 architecture
3. [ ] Migration guide created and tested
4. [ ] Architecture documentation updated
5. [ ] CHANGELOG.md includes breaking changes
6. [ ] All examples tested and working
7. [ ] All links verified as valid
8. [ ] No emoji or icons in documentation
9. [ ] Technical review completed
10. [ ] User review completed

## Notes

### Conversation Context
Final step in legacy infrastructure removal.
Must accurately reflect all changes made in v8.0.

### Key Documentation Principles
- Clarity over completeness
- Examples over explanations
- Actionable error messages
- Progressive disclosure

### Implementation Tips
- Use diff tools to find all legacy mentions
- Test every single example
- Have someone unfamiliar test migration guide
- Keep old docs in archive folder

## Time Tracking

### Estimates
- README updates: 2 hours
- CLAUDE.md updates: 1 hour
- Migration guide: 2 hours
- Architecture docs: 1 hour
- CHANGELOG: 30 minutes
- Testing: 30 minutes
- **Total**: 7 hours

### Actual
- Start Date: TBD
- End Date: TBD
- Actual Hours: TBD

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial story creation |