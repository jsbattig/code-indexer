# Release Notes

## Version 4.0.0.2 - Docker Cleanup Bug Fix

**Release Date**: September 4, 2025

### 🐛 Critical Bug Fix

- **Fixed Docker container cleanup in uninstall**: Resolved critical issue where `cidx uninstall --force-docker` left dangling containers that prevented subsequent startups
- **Enhanced container discovery**: Uninstall now finds and removes ALL containers with project hash, not just predefined ones
- **Project scoping protection**: Fixed dangerous cross-project container removal that could affect other CIDX projects
- **Container state handling**: Enhanced cleanup to properly handle containers in Created, Running, Exited, and Paused states
- **Orphan removal**: Added `--remove-orphans` flag to docker-compose down for complete cleanup

### 🔧 Technical Improvements

- **Project-scoped filtering**: Container cleanup now uses `name=cidx-{project_hash}-` instead of dangerous `name=cidx-` wildcards
- **Comprehensive validation**: Added validation to verify complete container removal after uninstall
- **Enhanced error reporting**: Improved verbose output with actionable guidance for manual cleanup
- **Mandatory force cleanup**: Uninstall operations always perform thorough container cleanup regardless of compose down results
- **Thread safety**: Fixed type issues and ensured atomic container operations

### 🧪 Code Quality

- **Deprecated datetime warnings**: Fixed all `datetime.utcnow()` deprecation warnings with `datetime.now(timezone.utc)`
- **Test suite improvements**: Updated tests to validate correct behavior instead of old buggy behavior
- **Zero warnings policy**: Eliminated all deprecation warnings from test suite
- **Fast automation pipeline**: All 1,239 unit tests passing with zero warnings

### 📖 Documentation

- **Installation Instructions**: Updated with version 4.0.0.2
- **Manual test plan**: Added comprehensive manual testing procedures for Docker cleanup validation

---

## Version 4.0.0.1 - Bug Fixes and Improvements

**Release Date**: September 4, 2025

### 🐛 Bug Fixes

- **Fixed cidx query permission issues**: Resolved silent failures when running queries as different users due to Git "dubious ownership" protection
- **Improved error messages**: Query operations now provide clearer feedback when git permission issues occur
- **Enhanced git-aware functionality**: All git operations now use the proper git_runner utility to handle ownership issues automatically

### 🔧 Technical Improvements

- **Type Safety**: Fixed all mypy type checking errors across the codebase (50+ errors resolved)
- **Code Quality**: Added proper type annotations and None checks throughout test and production code
- **Linting**: All files now pass ruff, black, and mypy checks without errors
- **Dependencies**: Updated development dependencies to include proper type stubs

### 📖 Documentation

- **Installation Instructions**: Updated with version 4.0.0.1
- **Troubleshooting**: Improved error handling provides better user guidance

---

## Version 4.0.0.0 - Multi-User Server Release

**Release Date**: September 2, 2025

### 🚀 NEW Major Features

- **Multi-User Server**: Complete FastAPI-based server implementation with JWT authentication
- **Role-Based Access Control**: Admin, power_user, and normal_user roles with different permissions
- **Golden Repository Management**: Centralized repository management system
- **Repository Activation**: Copy-on-Write cloning system for user workspaces
- **Advanced Query API**: Semantic search endpoints with file extension filtering
- **Background Job System**: Async processing for long-running operations
- **Health Monitoring**: Comprehensive system health and performance endpoints

### 🔧 Technical Improvements

- **JWT Authentication**: Secure token-based authentication with role verification
- **Copy-on-Write Cloning**: Efficient repository cloning with proper git structure preservation
- **File Extension Filtering**: Enhanced semantic search with file type filtering
- **Branch Operations**: Smart branch switching for local and remote repositories
- **Error Handling**: Consistent HTTP error responses across all endpoints
- **API Documentation**: Complete OpenAPI/Swagger documentation at `/docs`

### 🏗️ Architecture Changes

- **FastAPI Integration**: Full REST API implementation
- **Repository Isolation**: User-specific repository workspaces
- **Async Job Processing**: Background task management system
- **Database-Free Design**: File-system based user and repository management
- **Container Integration**: Seamless Docker/Podman container orchestration

### 🐛 Bug Fixes

- **Pagination Removal**: Removed unnecessary pagination from repository listing
- **Branch Switching**: Fixed git operations for CoW repositories
- **Repository Refresh**: Proper handling of --force flag in workflow operations
- **DELETE Error Handling**: Consistent HTTP status codes for delete operations
- **Mock Data Enhancement**: Diverse file types for comprehensive testing

### 🧪 Testing Enhancements

- **Manual Testing Epic**: Comprehensive 264 test case validation
- **End-to-End Testing**: Complete server functionality validation
- **Integration Testing**: Full API endpoint coverage
- **Unit Test Coverage**: 1366+ passing unit tests
- **Static Analysis**: Code quality and import validation

### 📚 Documentation Updates

- **Server Usage Guide**: Complete multi-user server documentation
- **API Examples**: Curl-based usage examples
- **Authentication Guide**: JWT token usage and role explanations
- **Installation Instructions**: Updated with version 4.0.0.0

### ⚠️ Breaking Changes

- **Server Mode**: New server functionality requires separate startup process
- **Authentication Required**: Server endpoints require JWT authentication
- **Repository Structure**: Golden repository management changes workspace organization

### 🔄 Migration Guide

For existing users upgrading to v4.0.0.0:

1. **CLI Usage**: All existing CLI commands remain unchanged and fully functional
2. **Server Usage**: New optional server mode requires separate setup
3. **Configuration**: Existing configurations remain compatible
4. **Data**: No migration required for existing indexed data

---

## Previous Versions

### Version 3.1.2.0
- Smart indexing improvements
- Git-aware processing enhancements
- VoyageAI integration
- Multi-project support

### Version 3.0.0.0
- Fixed-size chunking system
- Model-aware chunk sizing
- Breaking changes to semantic filtering
- Re-indexing recommended for optimal performance