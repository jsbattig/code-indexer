# User Story: Exact Branch Matching

## 📋 **User Story**

As a **CIDX user**, I want **automatic linking to remote repositories that have my exact local branch**, so that **I get the most relevant results without manual repository selection**.

## 🎯 **Business Value**

Provides optimal user experience by automatically connecting to repositories that match the user's current development context. Eliminates manual repository selection when exact matches exist.

## 📝 **Acceptance Criteria**

### Given: Local Branch Detection
**When** I query remote repositories from my local git repository  
**Then** the system detects my current local branch automatically  
**And** uses branch name for exact matching with remote repositories  
**And** handles detached HEAD state gracefully  
**And** provides clear indication of local branch context  

### Given: Exact Branch Matching Priority
**When** I have multiple repository options available  
**Then** activated repositories with exact branch match get highest priority  
**And** golden repositories with exact branch match are considered second  
**And** exact matches take precedence over fallback strategies  
**And** matching decision is communicated clearly to user  

### Given: Repository Discovery Integration
**When** I initiate first query in remote mode  
**Then** system discovers remote repositories using git origin URL  
**And** filters discovered repositories for exact branch matches  
**And** selects best match based on repository type and branch availability  
**And** stores linking decision for future queries  

### Given: Match Confirmation and Storage
**When** I establish exact branch match connection  
**Then** system displays matched repository and branch information  
**And** stores repository link in remote configuration  
**And** uses stored link for subsequent queries without re-discovery  
**And** provides option to change linked repository if needed  

## 🏗️ **Technical Implementation**

### Exact Branch Matching Logic
```python
class ExactBranchMatcher:
    def __init__(self, git_service: GitTopologyService, linking_client: RepositoryLinkingClient):
        self.git_service = git_service
        self.linking_client = linking_client
    
    async def find_exact_branch_match(self, local_repo_path: Path, repo_url: str) -> Optional[RepositoryLink]:
        # Get current local branch
        local_branch = self.git_service.get_current_branch()
        if not local_branch:
            return None
        
        # Discover remote repositories
        discovery_response = await self.linking_client.discover_repositories(repo_url)
        
        # Filter for exact branch matches
        exact_matches = self._filter_exact_matches(discovery_response, local_branch)
        
        # Prioritize activated over golden repositories
        best_match = self._select_best_match(exact_matches)
        
        return best_match
    
    def _filter_exact_matches(self, discovery_response: RepositoryDiscoveryResponse, target_branch: str) -> List[RepositoryMatch]:
        exact_matches = []
        
        # Check activated repositories first
        for repo in discovery_response.activated_repositories:
            if target_branch in repo.available_branches:
                exact_matches.append(RepositoryMatch(
                    alias=repo.alias,
                    repository_type="activated",
                    branch=target_branch,
                    match_quality="exact",
                    priority=1  # Highest priority for activated repos
                ))
        
        # Check golden repositories
        for repo in discovery_response.golden_repositories:
            if target_branch in repo.available_branches:
                exact_matches.append(RepositoryMatch(
                    alias=repo.alias,
                    repository_type="golden",
                    branch=target_branch,
                    match_quality="exact",
                    priority=2  # Lower priority, needs activation
                ))
        
        return exact_matches
```

## 📊 **Definition of Done**

- ✅ Local branch detection with git repository integration
- ✅ Remote repository discovery using git origin URL
- ✅ Exact branch name matching with activated and golden repositories
- ✅ Priority-based selection (activated > golden repositories)
- ✅ Repository link storage in remote configuration
- ✅ Clear user communication of matching decisions
- ✅ Integration with existing GitTopologyService
- ✅ Comprehensive testing including edge cases
- ✅ Error handling for git operations and API failures
- ✅ User experience validation with clear success feedback