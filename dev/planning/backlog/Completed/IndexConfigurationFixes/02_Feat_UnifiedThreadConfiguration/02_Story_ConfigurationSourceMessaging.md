# Story 2: Configuration Source Messaging

## User Story

**As a developer monitoring system configuration**, I want clear messaging about where thread count settings come from (CLI, config.json, or defaults), so that I understand how the system determined my thread configuration and can troubleshoot configuration issues.

## Acceptance Criteria

### Given I set thread count via CLI option `--parallel-vector-worker-thread-count 16`
### When the indexing operation starts
### Then I should see "🧵 Vector calculation threads: 16 (from CLI option)"
### And the message should clearly indicate the CLI option was used
### And any config.json setting should be noted as overridden if applicable

### Given I set `parallel_requests: 12` in config.json without CLI options
### When the indexing operation starts  
### Then I should see "🧵 Vector calculation threads: 12 (from config.json)"
### And the message should clearly indicate config.json was the source
### And no misleading "auto-detected" messaging should appear

### Given no thread configuration is provided anywhere
### When the indexing operation starts
### Then I should see "🧵 Vector calculation threads: 8 (default for voyage-ai)"
### And the message should clearly indicate this is a provider default
### And no suggestion of "detection" should appear in messaging

### Given invalid thread configuration is provided (e.g., negative numbers, exceeds system limits)
### When the system validates the configuration
### Then I should see clear error message: "❌ Invalid thread count: 32 (exceeds system limit of 16)"
### And the system should fall back to nearest valid value with explanation
### And fallback reasoning should be clearly communicated

## Technical Requirements

### Pseudocode Implementation
```
ConfigurationSourceMessaging:
    generate_thread_count_message(thread_config):
        base_message = f"🧵 Vector calculation threads: {thread_config.count}"
        
        source_descriptions = {
            "cli_option": "from CLI option",
            "config_json": "from config.json", 
            "provider_default": f"default for {thread_config.provider}",
            "system_limit": f"limited by system (requested {thread_config.requested})"
        }
        
        source_text = source_descriptions[thread_config.source]
        return f"{base_message} ({source_text})"
    
    validate_and_explain_thread_count(requested_count, system_limits):
        if requested_count > system_limits.max_threads:
            limited_count = system_limits.max_threads
            return ThreadConfig(
                count=limited_count, 
                source="system_limit",
                requested=requested_count
            )
        return ThreadConfig(count=requested_count, source="user_provided")
```

### Message Examples
```
CLI Override:
🧵 Vector calculation threads: 16 (from CLI option)

Config.json Setting:
🧵 Vector calculation threads: 12 (from config.json)

Provider Default:
🧵 Vector calculation threads: 8 (default for voyage-ai)

System Limited:
🧵 Vector calculation threads: 16 (limited by system, requested 32)

Configuration Override Notice:
🧵 Vector calculation threads: 16 (from CLI option, overriding config.json: 12)
```

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] CLI option source clearly indicated in messaging
- [ ] Config.json source clearly indicated when used
- [ ] Provider default source clearly indicated for fallback
- [ ] No misleading "auto-detected" messaging for hardcoded defaults
- [ ] Invalid configuration errors clearly explained
- [ ] Fallback reasoning clearly communicated to users
- [ ] Configuration override scenarios properly explained
- [ ] Source information accurate and helpful for troubleshooting

## Testing Requirements

### Unit Tests Required:
- Message generation for different configuration sources
- Thread configuration source detection accuracy
- Invalid configuration handling and messaging
- Configuration override scenarios

### Integration Tests Required:
- End-to-end messaging with various configuration sources
- CLI option override behavior with clear messaging
- Config.json configuration respect and messaging
- Default fallback messaging accuracy