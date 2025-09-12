# Story 1: Clear Index Operation Messaging

## User Story

**As a developer running indexing operations**, I want clear, non-redundant messaging about index operations, so that I understand what the system is actually doing without being confused by duplicate or misleading messages.

## Acceptance Criteria

### Given I run `cidx start` in a fresh repository
### When payload indexes are created for the first time
### Then I should see clear creation messaging: "🔧 Setting up payload indexes for optimal query performance..."
### And success confirmation: "📊 Successfully created all 7 payload indexes"
### And the messaging should indicate this is initial setup

### Given I run `cidx index` after indexes already exist
### When the system verifies existing payload indexes
### Then I should see verification messaging: "✅ Verified 7 payload indexes" or silent verification
### And I should NOT see duplicate "Creating index" messages for existing indexes
### And the system should clearly indicate indexes already exist

### Given some payload indexes are missing (edge case)
### When `cidx index` detects missing indexes
### Then I should see specific messaging: "🔧 Creating 2 missing payload indexes..."
### And only the missing indexes should be created
### And clear indication of what was missing and what was created

## Technical Requirements

### Pseudocode Implementation
```
ClearIndexMessaging:
    handle_collection_creation_context():
        show_message("🔧 Setting up payload indexes for optimal query performance...")
        create_all_indexes_with_progress()
        show_success("📊 Successfully created all 7 payload indexes")
    
    handle_index_verification_context():
        existing_count = count_existing_indexes()
        missing_indexes = find_missing_indexes()
        
        if missing_indexes:
            show_message(f"🔧 Creating {len(missing_indexes)} missing payload indexes...")
            create_missing_indexes()
            show_success(f"📊 Created {len(missing_indexes)} missing indexes")
        else:
            # Silent verification or brief confirmation
            if verbose_mode:
                show_message(f"✅ Verified {existing_count} payload indexes")
    
    handle_query_context():
        # Silent operation for read-only queries
        create_missing_indexes_silently()
```

### Message Examples
```
Collection Creation:
🔧 Setting up payload indexes for optimal query performance...
✅ Created 7 payload indexes

Index Verification (all exist):
✅ Verified 7 payload indexes (or silent)

Index Verification (2 missing):  
🔧 Creating 2 missing payload indexes...
✅ Created 2 missing indexes

Query Context:
[Silent index verification]
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] Clear creation messaging for fresh repository setup
- [ ] Verification messaging for existing indexes (not creation messaging)
- [ ] No duplicate "Creating index" messages for existing indexes
- [ ] Specific messaging for missing index scenarios
- [ ] Silent verification option for read-only contexts
- [ ] Context-appropriate messaging for different operation types
- [ ] Clear distinction between creation and verification operations

## Testing Requirements

### Unit Tests Required:
- Message generation for different index contexts
- Existing vs missing index detection and messaging
- Context-appropriate feedback mechanisms
- Message consistency and accuracy

### Integration Tests Required:
- End-to-end messaging during fresh repository setup
- Index verification messaging during normal operations
- Missing index detection and creation messaging