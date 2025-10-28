# Story 1: Centralized Index Creation

## User Story

**As a system administrator configuring code indexing**, I want all payload index operations to go through a single, centralized method, so that index creation logic is consistent and not duplicated across different commands.

## Acceptance Criteria

### Given the system needs to create or verify payload indexes
### When any command requires index operations (start, index, query)
### Then all operations should use the centralized `ensure_payload_indexes()` method
### And index creation logic should not be duplicated in multiple code paths
### And the centralized method should handle all contexts appropriately
### And no direct calls to underlying index creation should bypass the central method

### Given index creation is required for a new collection
### When `cidx start` creates a collection for the first time
### Then it should use the centralized index management system
### And index creation should be properly coordinated with collection setup
### And success/failure should be handled consistently

## Technical Requirements

### Pseudocode Implementation
```
CentralizedIndexManager:
    ensure_payload_indexes(collection_name, context):
        existing_indexes = check_existing_indexes(collection_name)
        required_indexes = get_required_indexes_from_config()
        missing_indexes = find_missing_indexes(required_indexes, existing_indexes)
        
        if context == "collection_creation":
            create_all_indexes_with_full_messaging(required_indexes)
        elif context == "index_verification":
            if missing_indexes:
                create_missing_indexes_with_feedback(missing_indexes)
            else:
                show_verification_message_or_silent()
        elif context == "query_verification":
            create_missing_indexes_silently(missing_indexes)
        
    remove_duplicate_index_creation():
        eliminate direct calls to _create_payload_indexes_with_retry()
        route all operations through ensure_payload_indexes()
        consolidate messaging and error handling
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] All payload index operations use centralized `ensure_payload_indexes()` method
- [ ] Index creation logic not duplicated across multiple code paths
- [ ] Centralized method handles all contexts appropriately
- [ ] No direct calls to underlying index creation bypass central method
- [ ] Collection creation uses centralized index management system
- [ ] Index creation properly coordinated with collection setup
- [ ] Success/failure handled consistently across all operations

## Testing Requirements

### Unit Tests Required:
- Centralized index manager initialization and configuration
- Context-based index operation routing
- Integration with existing collection creation flow
- Error handling consolidation

### Integration Tests Required:
- End-to-end index creation through centralized system
- Multiple command types using same centralized logic
- Index operation consistency across different contexts