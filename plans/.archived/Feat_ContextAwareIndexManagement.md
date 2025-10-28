# Feature 1: Context-Aware Index Management

## Feature Overview

Centralize payload index creation logic and implement context-aware messaging to eliminate duplicate index creation between `cidx start` and `cidx index` operations.

## Technical Architecture

### Component Design
- **Centralized Index Manager**: Single point of control for all index operations
- **Context Detection**: Differentiate between collection creation, indexing, and verification scenarios
- **Existence Checking**: Verify index existence before creation attempts
- **Smart Messaging**: Appropriate messages for different contexts

### Index Operation Contexts
1. **Collection Creation**: First-time setup, create all indexes with full messaging
2. **Index Verification**: Indexing operation, verify existing or create missing
3. **Query Verification**: Read-only, silent verification

## User Stories (Implementation Order)

### Story Implementation Checklist:
- [ ] 01_Story_CentralizedIndexCreation
- [ ] 02_Story_IndexExistenceChecking
- [ ] 03_Story_ContextAwareMessaging

## Dependencies
- **Prerequisites**: None (foundational feature)
- **Dependent Features**: Enhanced user feedback relies on this foundation

## Definition of Done
- [ ] All index creation centralized through single method
- [ ] Index existence checking implemented before creation attempts
- [ ] Context-aware messaging for different operation types
- [ ] Duplicate index creation eliminated between start and index commands
- [ ] Idempotent operations with appropriate user feedback