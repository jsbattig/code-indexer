# Feature: Comprehensive Command Mode Mapping

## 🎯 **Feature Overview**

Implement intelligent command routing that automatically detects local vs remote mode and routes commands through appropriate execution paths. Ensures identical UX between modes while gracefully handling commands that aren't compatible with remote mode.

This feature establishes the foundational architecture for hybrid local/remote operation, ensuring users have a seamless experience regardless of whether they're querying local indexes or remote repositories.

## 🏗️ **Technical Architecture**

### Command Detection and Routing

**Mode Detection Logic:**
```python
class CommandModeDetector:
    def detect_mode(self, project_path: Path) -> Literal["local", "remote", "uninitialized"]:
        # Check for remote configuration
        if (project_path / ".code-indexer" / ".remote-config").exists():
            return "remote"
        
        # Check for local configuration  
        if (project_path / ".code-indexer" / "config.toml").exists():
            return "local"
            
        return "uninitialized"
```

**Command Routing Architecture:**
```python
@cli.command("query")
@click.pass_context
def query_command(ctx, query_text: str, **options):
    mode = detect_mode(ctx.obj.codebase_dir)
    
    if mode == "remote":
        return execute_remote_query(query_text, **options)
    elif mode == "local":
        return execute_local_query(query_text, **options)
    else:
        raise ClickException("Repository not initialized")
```

### API Client Abstraction Layer

**Clean HTTP Client Architecture:**
```python
# Base API client with authentication and error handling
class CIDXRemoteAPIClient:
    def __init__(self, server_url: str, credentials: EncryptedCredentials):
        self.server_url = server_url
        self.credentials = credentials
        self.session = httpx.AsyncClient()
        self.jwt_manager = JWTManager()
    
    async def authenticated_request(self, method: str, endpoint: str, **kwargs):
        # Handle JWT token management, refresh, re-authentication
        # Centralized error handling and retry logic
        # No business logic - pure HTTP client functionality

# Specialized clients for specific functionality
class RepositoryLinkingClient(CIDXRemoteAPIClient):
    async def discover_repositories(self, repo_url: str) -> RepositoryDiscoveryResponse:
        # Repository discovery and linking operations
        
class RemoteQueryClient(CIDXRemoteAPIClient):
    async def execute_query(self, query: str, **options) -> List[QueryResultItem]:
        # Remote semantic search operations
```

## 📋 **Dependencies**

### Feature Prerequisites
- **Feature 0**: API Server Enhancements (completed)
  - Repository discovery endpoint
  - Enhanced query results with timestamps
  - Golden repository branch listing

### External Dependencies
- Existing Click CLI framework and command structure
- GitTopologyService for git-aware operations
- Configuration management system (.code-indexer directory)
- Credential encryption and storage capabilities

## 🎯 **Business Value**

### Seamless User Experience
- **Transparent Operation**: Users don't need to think about local vs remote mode
- **Consistent Commands**: Identical syntax and behavior across modes
- **Clear Error Messages**: When commands aren't available, users understand why
- **Graceful Degradation**: Network issues don't crash the application

### Clean Architecture Foundation
- **Maintainable Code**: Clean separation between HTTP clients and business logic
- **Testable Components**: API clients easily mocked for unit testing
- **Extensible Design**: New remote operations easily added through client abstraction
- **Error Handling**: Centralized authentication and network error management

## ✅ **Acceptance Criteria**

### Mode Detection and Routing
- ✅ Automatic detection of local vs remote mode from configuration
- ✅ Commands route to appropriate execution path transparently
- ✅ Uninitialized repositories provide clear guidance
- ✅ Mode detection works across different project structures

### Command Compatibility Management
- ✅ Compatible commands (query, version, help) work identically in both modes
- ✅ Incompatible commands (start, stop, index, watch) provide clear error messages
- ✅ Status and uninstall commands adapted for remote mode context
- ✅ Error messages explain why commands are disabled and suggest alternatives

### API Client Architecture
- ✅ Clean abstraction layer with no raw HTTP calls in business logic
- ✅ Centralized authentication and JWT token management
- ✅ Specialized clients for different remote operations
- ✅ Comprehensive error handling and retry logic
- ✅ Easily mockable for unit testing

### User Experience Consistency
- ✅ Query operations have identical syntax and output format
- ✅ Help and version commands work the same regardless of mode
- ✅ Error messages provide actionable guidance
- ✅ No surprising behavior differences between modes

## 🧪 **Testing Strategy**

### Unit Tests
- Mode detection logic with various configuration scenarios
- Command routing decisions based on detected mode
- API client abstraction layer functionality
- Error handling for network and authentication failures

### Integration Tests
- End-to-end command execution in both local and remote modes
- Mode switching behavior and configuration persistence
- API client integration with actual server endpoints
- Error handling with real network and authentication scenarios

### User Experience Tests
- Command syntax consistency across modes
- Error message clarity and actionability
- Help system accuracy for both modes
- Configuration management and mode persistence

## 📊 **Story Implementation Order**

| Story | Priority | Dependencies |
|-------|----------|--------------|
| **01_Story_CommandModeDetection** | Critical | Foundation for all other stories |
| **02_Story_DisabledCommandHandling** | High | User experience requirement |
| **03_Story_AdaptedCommandBehavior** | High | Remote mode functionality |
| **04_Story_APIClientAbstraction** | Critical | Architecture foundation |

**Implementation Strategy**: Stories 1 and 4 provide the foundation, while stories 2 and 3 build user-facing functionality on top of the architecture.

## 🔧 **Implementation Notes**

### Configuration Management
- Remote mode configuration stored in `.code-indexer/.remote-config`
- Local mode configuration in `.code-indexer/config.toml` (existing)
- Mode detection through file existence and validity checks
- Graceful handling of partial or corrupted configurations

### Command Execution Strategy
- Preserve existing local command implementations
- Add remote command implementations as parallel execution paths
- Use Click context to pass mode information throughout command chain
- Maintain backward compatibility with existing local-only installations

### Error Handling Philosophy
- Fail fast with clear error messages rather than confusing partial functionality
- Provide actionable guidance for resolving issues
- Network errors suggest checking connectivity and credentials
- Authentication errors guide users to credential management commands

### API Client Design Principles
- Single responsibility: each client handles one type of operation
- Dependency injection: clients receive configuration rather than loading it
- Error transparency: let business logic handle API errors appropriately
- Resource management: proper connection pooling and cleanup