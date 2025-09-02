# Release Notes

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