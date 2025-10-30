# Feature: Core Resilience

## Overview

Fundamental persistence and recovery mechanisms providing durable queue state, job reattachment capabilities, cleanup operation resumption, and startup failure detection. This feature establishes the foundation for crash resilience.

## Technical Architecture

### Components

- **Queue Persistence Engine**: Durable queue state storage
- **Job Reattachment Service**: Running job recovery
- **Cleanup State Manager**: Resumable cleanup operations
- **Startup Detection Service**: Failed startup identification
- **Recovery APIs**: Admin visibility and control

### Persistence Strategy

- Write-ahead logging for queue operations
- Sentinel files for job tracking
- State machines for cleanup operations
- Startup markers for detection
- Atomic operations for consistency

## Stories

1. **Queue Persistence with Recovery API** - Complete queue state durability and recovery
2. **Job Reattachment with Monitoring API** - Running job reconnection and monitoring
3. **Resumable Cleanup with State API** - Cleanup operation state preservation
4. **Aborted Startup Detection with Retry API** - Failed startup handling

## Dependencies

- Database for persistent storage
- File system for sentinel files
- Process management capabilities
- Existing job execution framework

## Success Metrics

- Queue recovery time: <10 seconds
- Job reattachment success rate: >95%
- Cleanup resumption accuracy: 100%
- Startup detection latency: <5 seconds
- API response time: <200ms