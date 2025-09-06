# Story 1: Thread Configuration Hierarchy

## User Story

**As a developer configuring multi-threaded processing**, I want the system to respect my thread count configuration from config.json instead of ignoring it in favor of hardcoded defaults, so that I can control system resource utilization according to my hardware and requirements.

## Acceptance Criteria

### Given I set `parallel_requests: 12` in my project's config.json
### When I run `cidx index` without CLI thread options
### Then the system should use 12 threads for vector calculation processing
### And the progress display should show "🧵 Vector calculation threads: 12 (from config.json)"
### And both VoyageAI HTTP threads and vector calculation threads should use the same configured value
### And the configuration source should be clearly indicated in the messaging

### Given I provide CLI option `--parallel-vector-worker-thread-count 16`  
### When I run `cidx index -p 16` with config.json setting of 12
### Then the CLI option should override the config.json setting
### And the system should use 16 threads for processing
### And the progress display should show "🧵 Vector calculation threads: 16 (from CLI option)"
### And the configuration precedence should be clearly communicated

### Given no thread configuration is provided anywhere
### When I run `cidx index` without CLI options or config.json settings
### Then the system should use provider-specific defaults
### And the progress display should show "🧵 Vector calculation threads: 8 (default for voyage-ai)"
### And the default behavior should be clearly indicated

## Technical Requirements

### Pseudocode Implementation
```
ThreadConfigurationManager:
    determine_thread_count(cli_option, config, provider):
        # Configuration precedence hierarchy
        if cli_option is not None:
            return ThreadConfig(count=cli_option, source="CLI option")
        elif config.voyage_ai.parallel_requests is not None:
            return ThreadConfig(count=config.parallel_requests, source="config.json")
        else:
            default_count = get_default_thread_count(provider)
            return ThreadConfig(count=default_count, source=f"default for {provider}")
    
    apply_thread_configuration(thread_config):
        configure_vector_calculation_manager(thread_config.count)
        configure_voyageai_client(thread_config.count)
        display_configuration_message(thread_config)
    
    display_configuration_message(thread_config):
        message = f"🧵 Vector calculation threads: {thread_config.count} ({thread_config.source})"
        console.print(message)
```

### Configuration Precedence
1. **Highest Priority**: CLI option `--parallel-vector-worker-thread-count`
2. **Medium Priority**: config.json `voyage_ai.parallel_requests`
3. **Lowest Priority**: Provider-specific defaults

## Definition of Done

### Acceptance Criteria Checklist:
- [ ] System respects config.json thread count instead of ignoring it
- [ ] CLI option overrides config.json setting when provided
- [ ] Configuration source clearly indicated in progress messaging
- [ ] Both HTTP and vector calculation threads use same configured value
- [ ] Provider defaults used only when no configuration provided
- [ ] Configuration precedence clearly communicated to users
- [ ] Thread count validation prevents invalid configurations

## Testing Requirements

### Unit Tests Required:
- Configuration precedence logic for different scenarios
- Thread count determination from various sources
- Configuration messaging accuracy
- Integration with VectorCalculationManager and VoyageAI client

### Integration Tests Required:
- End-to-end thread configuration with config.json settings
- CLI option override behavior
- Default fallback scenarios
- Multi-threaded processing with configured thread counts