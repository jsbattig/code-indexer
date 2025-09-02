# CIDX Multi-User Server Test Repository

This is a standardized test repository used for comprehensive testing of the CIDX multi-user server functionality.

## Contents

### Core Files

- `main.py` - Main application entry point with basic functionality
- `api.py` - REST API implementation with various endpoints
- `auth.py` - Authentication and authorization utilities
- `database.py` - Database models and connection handling
- `utils.py` - Common utility functions and helpers

### Feature Modules

- `features/search.py` - Search functionality implementation
- `features/indexing.py` - Code indexing and processing
- `features/analysis.py` - Code analysis and metrics
- `config/settings.py` - Configuration management
- `config/logging.py` - Logging configuration

### Test Support

- `tests/test_api.py` - API endpoint tests
- `tests/test_auth.py` - Authentication tests
- `docs/architecture.md` - System architecture documentation

## Semantic Search Test Data

This repository contains meaningful code examples designed to test semantic search capabilities:

- **Authentication patterns**: JWT handling, role-based access control
- **API patterns**: REST endpoints, request/response handling
- **Database patterns**: ORM models, connection management
- **Configuration patterns**: Settings management, environment handling
- **Error handling patterns**: Exception handling, logging

## Usage in Tests

The test data factory (`tests/utils/test_data_factory.py`) uses this repository to create:

1. **Clean test instances** - Fresh copies for each test
2. **Git repository state** - Proper git history and branches
3. **Consistent content** - Reliable semantic search results
4. **Isolation** - No test interference

## Git Structure

- `master` branch - Main development line
- `feature/search` branch - Search feature development
- `feature/auth` branch - Authentication feature work
- Multiple commits with realistic development history

This structure enables testing of git-aware indexing and branch-based functionality.