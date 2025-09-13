# Feature: API Server Enhancements

## 🎯 **Feature Overview**

**CRITICAL PREREQUISITE**: This feature contains server-side API enhancements that must be completed before any client-side remote mode development can begin. All remote functionality depends on these server capabilities.

Enhance the CIDX server with missing API endpoints and data model improvements required to support remote repository linking mode. These enhancements enable repository discovery by git origin URL, universal timestamp collection for staleness detection, and golden repository branch enumeration.

## 🏗️ **Technical Architecture**

### API Endpoint Enhancements

**Repository Discovery Endpoint:**
```python
@app.get("/api/repos/discover")
async def discover_repositories(repo_url: str) -> RepositoryDiscoveryResponse:
    """Find matching golden and activated repositories by git origin URL"""
    # Return both golden repo candidates and activated repo matches
    # Enable smart repository linking for remote clients
```

**Golden Repository Branch Listing:**
```python  
@app.get("/api/repos/golden/{alias}/branches")
async def list_golden_branches(alias: str) -> List[BranchInfo]:
    """Return available branches for golden repository before activation"""
    # Support intelligent branch selection during linking
```

### Data Model Enhancements

**QueryResultItem Enhancement:**
```python
class QueryResultItem(BaseModel):
    # Existing fields...
    file_last_modified: Optional[float] = None  # NEW: Unix timestamp
    indexed_timestamp: Optional[float] = None   # NEW: When file was indexed
    # Enable file-level staleness detection
```

**Universal Timestamp Collection:**
- Always collect `file_last_modified` from `file_path.stat().st_mtime` during indexing
- Store in vector database payload for both git and non-git projects
- Ensure timestamp availability for staleness comparison

## 📋 **Dependencies**

### Server-Side Prerequisites
- Existing JWT authentication system
- Repository management infrastructure  
- Vector database query system
- Git topology analysis capabilities

### Blocks Client Development
- **Feature 1**: Command mode mapping requires repository discovery API
- **Feature 3**: Smart repository linking needs branch listing endpoint
- **Feature 5**: Staleness detection depends on timestamp model enhancement
- **All Features**: Universal timestamp collection required for file-level staleness

## 🎯 **Business Value**

### Remote Mode Foundation
- **Repository Discovery**: Enable clients to find matching remote repositories
- **Branch Intelligence**: Support git-aware branch matching and fallbacks
- **Data Quality**: Provide timestamp data for staleness detection
- **API Completeness**: Fill gaps in server API for remote client support

### Team Collaboration Enablement
- **Golden Repository Access**: Teams can discover and link to shared indexes
- **Branch Flexibility**: Support multiple branch patterns and fallback strategies
- **Staleness Awareness**: Users know when local files differ from remote index
- **Seamless Integration**: Server provides all data needed for transparent remote UX

## ✅ **Acceptance Criteria**

### Repository Discovery API
- ✅ Endpoint accepts git origin URL and returns matching repositories
- ✅ Response includes both golden and activated repository candidates
- ✅ Supports HTTP and SSH git URL formats
- ✅ Returns empty results for unknown repositories (no errors)
- ✅ API authenticated and respects user permissions

### Universal Timestamp Collection  
- ✅ File modification timestamps collected during indexing for ALL files
- ✅ Works identically for git and non-git projects
- ✅ Timestamps stored in vector database payload
- ✅ QueryResultItem model includes timestamp fields
- ✅ Existing queries return timestamp data without breaking changes

### Golden Repository Branch Listing
- ✅ Endpoint returns available branches for specified golden repository
- ✅ Branch information includes name and basic metadata
- ✅ Handles repositories with no branches gracefully
- ✅ Authenticated endpoint respects repository access permissions
- ✅ Efficient query performance for repositories with many branches

## 🧪 **Testing Strategy**

### API Integration Tests
- Repository discovery with various git URL formats
- Branch listing for golden repositories with multiple branches
- Timestamp collection and retrieval during indexing operations
- Authentication and authorization for new endpoints

### Data Model Tests
- QueryResultItem serialization with new timestamp fields
- Backward compatibility with existing query responses
- Timestamp accuracy and timezone handling
- Vector database payload schema validation

### End-to-End Validation
- Complete indexing workflow with timestamp collection
- Query operations returning enhanced timestamp data
- Repository discovery integration with git topology analysis
- Branch listing accuracy against actual git repository state

## 📊 **Story Implementation Order**

| Story | Priority | Dependencies |
|-------|----------|--------------|
| **01_Story_RepositoryDiscoveryEndpoint** | Critical | Blocks Feature 1 & 3 |
| **02_Story_UniversalTimestampCollection** | Critical | Blocks Feature 5 |  
| **03_Story_GoldenRepositoryBranchListing** | High | Blocks Feature 3 |

**Critical Path**: All stories in this feature are prerequisites for client-side development. No client-side remote mode work can begin until these server enhancements are completed and tested.

## 🔧 **Implementation Notes**

### Repository Discovery Strategy
- Use git origin URL parsing and normalization
- Query existing repository metadata for URL matches
- Return structured data for client-side branch matching logic
- Consider HTTP/SSH URL equivalence (github.com vs git@github.com)

### Timestamp Collection Implementation
- Modify FileChunkingManager to always collect file modification time
- Update vector database schema to include timestamp fields
- Ensure QueryResultItem model enhancement maintains backward compatibility
- Test with both git and non-git project structures

### Branch Listing Optimization
- Efficient git branch enumeration for golden repositories
- Cache branch information to improve response times
- Handle edge cases (empty repositories, detached HEAD, etc.)
- Return branch metadata useful for intelligent client-side matching