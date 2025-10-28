# Feature 2: Unified Thread Configuration

## Feature Overview

Fix thread configuration split brain issue where user config.json settings are ignored in favor of hardcoded defaults, implementing proper configuration precedence hierarchy.

## Technical Architecture

### Component Design
- **Thread Configuration Manager**: Centralized thread count determination
- **Configuration Precedence**: CLI option → config.json → provider defaults
- **Source Tracking**: Clear indication of configuration source in messaging
- **Validation**: Thread count limits and hardware constraints

### Current Split Brain Issue
```
Layer 1: VoyageAI HTTP Pool
├─ Source: config.json (parallel_requests: 12) ✅ Working
├─ Usage: HTTP requests to VoyageAI API
└─ Result: Respects user configuration

Layer 2: Vector Calculation Manager  
├─ Source: Hardcoded defaults (8 threads) ❌ Broken
├─ Usage: Embedding computation orchestration
└─ Result: Ignores user configuration
```

### Target Unified Architecture
```
Configuration Sources (Precedence Order):
├─ CLI Option: --parallel-vector-worker-thread-count
├─ Config.json: voyage_ai.parallel_requests  
└─ Provider Default: get_default_thread_count()

Thread Pool Distribution:
├─ VoyageAI HTTP Pool: Uses determined count
└─ Vector Calculation Pool: Uses same determined count
```

## User Stories (Implementation Order)

### Story Implementation Checklist:
- [ ] 01_Story_ThreadConfigurationHierarchy
- [ ] 02_Story_ConfigurationSourceMessaging
- [ ] 03_Story_ThreadCountValidation

## Dependencies
- **Prerequisites**: None (independent feature)
- **Dependent Features**: Enhanced user feedback uses configuration source information

## Definition of Done
- [ ] VectorCalculationManager respects config.json parallel_requests setting
- [ ] Configuration precedence implemented (CLI → config → defaults)
- [ ] Misleading "auto-detected" messaging replaced with accurate source indication
- [ ] Both thread pools use consistent configuration
- [ ] Thread count validation with clear error messages
- [ ] Configuration source clearly displayed in progress messaging