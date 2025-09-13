# User Story: Branch Fallback Hierarchy

## 📋 **User Story**

As a **CIDX user on a feature branch**, I want **intelligent fallback to parent branches using git merge-base analysis**, so that **I can access relevant remote indexes even when my exact branch doesn't exist remotely**.

## 🎯 **Business Value**

Enables intelligent branch matching using git topology analysis. Users working on feature branches automatically connect to appropriate parent branch indexes (main, develop) when exact matches don't exist.

## 📝 **Acceptance Criteria**

### Given: Git Merge-Base Analysis
**When** exact branch matching fails  
**Then** system uses GitTopologyService to find feature branch origin  
**And** identifies parent branches through merge-base analysis  
**And** prioritizes long-lived branches (main, develop, master) over feature branches  
**And** provides clear explanation of fallback reasoning  

### Given: Intelligent Parent Branch Detection
**When** analyzing branch hierarchy  
**Then** system identifies common ancestor commits with long-lived branches  
**And** selects uppermost parent branch with remote availability  
**And** prefers activated repositories over golden repositories  
**And** handles complex git histories gracefully  

## 🏗️ **Technical Implementation**

```python
class BranchFallbackMatcher:
    def __init__(self, git_service: GitTopologyService):
        self.git_service = git_service
        self.long_lived_branches = ['main', 'master', 'develop', 'development', 'release']
    
    async def find_fallback_branch_match(self, local_repo_path: Path, discovery_response: RepositoryDiscoveryResponse) -> Optional[RepositoryLink]:
        local_branch = self.git_service.get_current_branch()
        
        # Get branch ancestry through merge-base analysis
        branch_ancestry = await self._analyze_branch_ancestry(local_branch)
        
        # Find best parent branch match in remote repositories
        for parent_branch in branch_ancestry:
            match = await self._find_parent_branch_match(parent_branch, discovery_response)
            if match:
                return match
        
        return None
    
    async def _analyze_branch_ancestry(self, current_branch: str) -> List[str]:
        # Use GitTopologyService to find merge-base with long-lived branches
        ancestry = []
        
        for long_lived_branch in self.long_lived_branches:
            if self._branch_exists(long_lived_branch):
                merge_base = self.git_service._get_merge_base(current_branch, long_lived_branch)
                if merge_base:
                    ancestry.append(long_lived_branch)
        
        # Sort by merge-base recency and branch priority
        return self._prioritize_parent_branches(ancestry)
```

## 📊 **Definition of Done**

- ✅ GitTopologyService integration for merge-base analysis
- ✅ Long-lived branch identification and prioritization
- ✅ Parent branch ancestry discovery through git history
- ✅ Remote repository matching with fallback branches
- ✅ Clear user communication of fallback decisions
- ✅ Comprehensive testing with complex git histories
- ✅ Performance optimization for large git repositories
- ✅ Error handling for git operation failures
- ✅ Integration with repository linking workflow