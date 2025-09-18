# User Story: Repository Discovery Endpoint

## 📋 **User Story**

As a **CIDX remote client**, I want to **discover matching repositories on the server by providing my local git origin URL**, so that **I can intelligently link to the appropriate golden or activated remote repository for my project**.

## 🎯 **Business Value**

Enables remote clients to automatically find matching repositories on the server without manual repository selection. Supports intelligent repository linking based on git origin URL analysis, eliminating the need for users to manually browse and select from potentially hundreds of remote repositories.

## 📝 **Acceptance Criteria**

### Given: Git Origin URL Repository Discovery
**When** I call `GET /api/repos/discover?repo_url={git_origin_url}`  
**Then** the endpoint returns matching golden and activated repositories  
**And** supports both HTTP and SSH git URL formats  
**And** handles URL normalization (github.com vs git@github.com)  
**And** returns empty list for unknown repositories (no errors)  

### Given: Repository Discovery Response Format
**When** I receive the discovery response  
**Then** the response includes repository type (golden/activated)  
**And** includes repository alias and metadata  
**And** provides branch information for intelligent matching  
**And** follows consistent API response structure  

### Given: Authentication and Authorization
**When** I make repository discovery requests  
**Then** the endpoint requires valid JWT authentication  
**And** respects user access permissions for repositories  
**And** only returns repositories the user can access  
**And** provides clear error messages for unauthorized access  

### Given: Performance and Reliability
**When** I query repository discovery with various URLs  
**Then** the endpoint responds within 2 seconds for typical requests  
**And** handles malformed git URLs gracefully with clear errors  
**And** supports concurrent discovery requests without issues  
**And** provides consistent results for identical URL queries  

## 🏗️ **Technical Implementation**

### API Endpoint Design
```python
@app.get("/api/repos/discover")
async def discover_repositories(
    repo_url: str,
    current_user: User = Depends(get_current_user)
) -> RepositoryDiscoveryResponse:
    """
    Find matching golden and activated repositories by git origin URL.
    
    Args:
        repo_url: Git origin URL (HTTP or SSH format)
        current_user: Authenticated user from JWT token
        
    Returns:
        RepositoryDiscoveryResponse with matching repositories
    """
    # Normalize git URL (HTTP/SSH equivalence)
    normalized_url = normalize_git_url(repo_url)
    
    # Query golden repositories
    golden_matches = await find_golden_repos_by_url(normalized_url, current_user)
    
    # Query activated repositories  
    activated_matches = await find_activated_repos_by_url(normalized_url, current_user)
    
    return RepositoryDiscoveryResponse(
        query_url=repo_url,
        normalized_url=normalized_url,
        golden_repositories=golden_matches,
        activated_repositories=activated_matches
    )
```

### Response Data Model
```python
class RepositoryMatch(BaseModel):
    alias: str
    repository_type: Literal["golden", "activated"]
    git_url: str
    available_branches: List[str]
    default_branch: Optional[str]
    last_indexed: Optional[datetime]
    
class RepositoryDiscoveryResponse(BaseModel):
    query_url: str
    normalized_url: str
    golden_repositories: List[RepositoryMatch]
    activated_repositories: List[RepositoryMatch]
    total_matches: int
```

### Git URL Normalization Logic
```python
def normalize_git_url(repo_url: str) -> str:
    """
    Normalize git URL to canonical form for matching.
    
    Examples:
        https://github.com/user/repo.git -> github.com/user/repo
        git@github.com:user/repo.git -> github.com/user/repo
        https://github.com/user/repo -> github.com/user/repo
    """
    # Remove protocol and credentials
    # Normalize SSH vs HTTPS format
    # Remove .git suffix
    # Return canonical domain/user/repo format
```

## 🧪 **Testing Requirements**

### Unit Tests
- ✅ Git URL normalization with various formats (HTTP, SSH, .git suffix)
- ✅ Repository matching logic with golden and activated repositories
- ✅ Authentication and authorization validation
- ✅ Error handling for malformed URLs and database issues

### Integration Tests  
- ✅ End-to-end API requests with real authentication
- ✅ Database queries for repository discovery
- ✅ Response format validation and consistency
- ✅ Performance testing with concurrent requests

### API Contract Tests
- ✅ Response schema validation against OpenAPI specification
- ✅ Error response format consistency
- ✅ Authentication requirement enforcement
- ✅ Query parameter validation and handling

## ⚠️ **Edge Cases and Error Handling**

### Malformed URLs
- Invalid git URL formats return 400 Bad Request with clear message
- Empty or null repo_url parameter handled gracefully
- Very long URLs (>2000 chars) rejected with appropriate error

### Repository Access Control
- Users only see repositories they have permission to access
- Private repositories require explicit user access
- Golden repositories respect organizational access controls

### Performance Considerations
- Database queries optimized with appropriate indexes
- URL normalization cached to avoid repeated computation
- Response size limited to prevent memory issues with many matches

### Network and Database Failures
- Database connection issues return 500 with retry guidance
- Timeout handling for slow repository metadata queries
- Graceful degradation when repository service unavailable

## 📊 **Definition of Done**

- ✅ API endpoint implemented and tested with comprehensive unit tests
- ✅ Git URL normalization handles HTTP, SSH, and edge case formats
- ✅ Repository matching works for both golden and activated repositories
- ✅ Authentication and authorization properly enforced
- ✅ Response format matches specification and includes all required fields
- ✅ Performance testing confirms <2 second response times
- ✅ Integration tests validate end-to-end functionality
- ✅ Error handling covers all identified edge cases
- ✅ API documentation updated with endpoint specification
- ✅ Code review completed with security and performance validation