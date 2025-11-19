# Feature: Documentation Updates

## Feature ID
`FEAT-DOCS-UPDATE-001`

## Parent Epic
`EPIC-LEGACY-REMOVAL-001`

## Title
Update Documentation for Simplified Architecture

## Status
PLANNED

## Priority
LOW

## Feature Owner
TBD

## Feature Summary

Update all project documentation to reflect the simplified architecture after removal of legacy infrastructure. This includes updating the README, CLAUDE.md, architecture documents, and creating a migration guide for users upgrading from previous versions. Documentation must accurately describe the container-free, filesystem-only backend with VoyageAI as the sole embedding provider.

## Business Value

### Benefits
- Clear documentation prevents user confusion
- Migration guide enables smooth upgrades
- Simplified docs reduce onboarding time
- Accurate architecture docs aid contributors
- Reduced documentation maintenance burden

### Impact
- **Users**: Clear upgrade path and usage instructions
- **Contributors**: Accurate architecture understanding
- **Support**: Fewer questions about deprecated features

## Technical Requirements

### Functional Requirements
1. Update README.md to remove legacy references
2. Update CLAUDE.md project instructions
3. Update architecture documentation
4. Create migration guide for v8.0.0
5. Update installation instructions
6. Add CHANGELOG entry for breaking changes

### Non-Functional Requirements
- Documentation must be accurate and complete
- Examples must work with new architecture
- Migration guide must be actionable
- Links must be valid and working

### Technical Constraints
- Must maintain documentation structure
- Cannot break existing documentation links
- Must follow project documentation standards

## Scope

### Included
- README.md updates
- CLAUDE.md updates
- Architecture document updates
- Migration guide creation
- CHANGELOG.md entry
- Installation instruction updates
- Example configuration updates

### Excluded
- API documentation generation
- External documentation sites
- Video tutorials or demos

## Dependencies

### Technical Dependencies
- Final CLI interface from Feature 4
- Test structure from Feature 5
- All code changes must be complete

### Feature Dependencies
- Must complete after all other features (1-5)

## Architecture & Design

### Documentation Structure
```
project-root/
├── README.md                      # Main project documentation
├── CLAUDE.md                      # Claude-specific instructions
├── CHANGELOG.md                   # Version history
├── docs/
│   ├── architecture/
│   │   └── v8.0.0-simplified.md  # New architecture doc
│   ├── migration/
│   │   └── migration-to-v8.md    # Migration guide
│   └── installation.md           # Installation instructions
```

### Key Documentation Changes
1. Remove all references to Qdrant
2. Remove all references to containers
3. Remove all references to Ollama
4. Update CLI command examples
5. Simplify configuration examples
6. Update architecture diagrams

## Implementation Approach

### Phase 1: README Updates
- Remove legacy feature mentions
- Update installation instructions
- Simplify usage examples

### Phase 2: CLAUDE.md Updates
- Remove deprecated mode descriptions
- Update architecture details
- Simplify configuration section

### Phase 3: Architecture Docs
- Create new simplified architecture doc
- Archive old architecture docs
- Update diagrams if needed

### Phase 4: Migration Guide
- Document breaking changes
- Provide step-by-step migration
- Include troubleshooting section

## Stories

### Story 1: Update Documentation
- Update all documentation files
- Create migration guide
- Verify all examples work
- **Estimated Effort**: 1 day

## Acceptance Criteria

1. README.md has no legacy infrastructure references
2. CLAUDE.md accurately describes v8.0 architecture
3. Migration guide created and comprehensive
4. CHANGELOG.md includes breaking changes
5. All examples tested and working
6. All documentation links valid
7. Installation instructions updated
8. Architecture docs reflect simplified design

## Test Strategy

### Documentation Testing
- Test all code examples
- Verify all commands work
- Check all links are valid
- Test migration guide steps

### Review Process
- Technical review for accuracy
- User review for clarity
- Final review for completeness

## Risks & Mitigations

### Risk 1: Incomplete Documentation
- **Impact**: HIGH
- **Mitigation**: Systematic review checklist

### Risk 2: Confusing Migration
- **Impact**: MEDIUM
- **Mitigation**: Step-by-step guide with examples

## Notes

### Conversation Context
Final phase of legacy infrastructure removal.
Documentation must reflect all changes made.

### Implementation Order
- Last phase after all code changes
- Low priority but essential
- Must be complete for v8.0.0 release

## Revision History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-19 | 1.0 | System | Initial feature specification |