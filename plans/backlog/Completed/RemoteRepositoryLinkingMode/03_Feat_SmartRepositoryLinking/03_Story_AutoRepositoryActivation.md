# User Story: Auto-Repository Activation

## 📋 **User Story**

As a **CIDX user**, I want **automatic repository activation when only golden repositories match**, so that **I can access remote indexes without manual activation steps**.

## 🎯 **Business Value**

Streamlines user experience by automatically activating golden repositories when needed. Eliminates manual activation workflow while providing transparency and control over activation decisions.

## 📝 **Acceptance Criteria**

### Given: Golden Repository Auto-Activation
**When** only golden repositories match my branch criteria  
**Then** system automatically activates the best-match golden repository  
**And** generates meaningful user alias with branch context  
**And** confirms activation success before proceeding with queries  
**And** handles activation failures with fallback options  

### Given: User Alias Generation
**When** activating golden repository automatically  
**Then** system generates descriptive alias combining project and branch context  
**And** ensures alias uniqueness across user's activated repositories  
**And** provides option for user to customize generated alias  
**And** stores alias mapping for future reference  

### Given: Activation Transparency
**When** auto-activation occurs  
**Then** system clearly communicates activation decision to user  
**And** displays activated repository details and alias  
**And** provides option to change activation if desired  
**And** explains benefits of activation for ongoing queries  

## 🏗️ **Technical Implementation**

```python
class AutoRepositoryActivator:
    def __init__(self, linking_client: RepositoryLinkingClient):
        self.linking_client = linking_client
    
    async def auto_activate_golden_repository(
        self, 
        golden_repo: RepositoryMatch, 
        project_context: Path
    ) -> ActivatedRepository:
        # Generate meaningful user alias
        user_alias = self._generate_user_alias(golden_repo, project_context)
        
        # Confirm with user (optional based on configuration)
        if not self._confirm_activation(golden_repo, user_alias):
            raise UserCancelledActivationError()
        
        # Activate repository
        activated_repo = await self.linking_client.activate_repository(
            golden_alias=golden_repo.alias,
            branch=golden_repo.branch,
            user_alias=user_alias
        )
        
        # Display success information
        self._display_activation_success(activated_repo)
        
        return activated_repo
    
    def _generate_user_alias(self, golden_repo: RepositoryMatch, project_context: Path) -> str:
        project_name = project_context.name
        branch_name = golden_repo.branch
        
        # Generate descriptive alias: projectname-branchname-timestamp
        timestamp = datetime.now().strftime("%m%d")
        base_alias = f"{project_name}-{branch_name}-{timestamp}"
        
        # Ensure uniqueness (add suffix if needed)
        return self._ensure_unique_alias(base_alias)
```

## 📊 **Definition of Done**

- ✅ Auto-activation logic for golden repositories
- ✅ User alias generation with project and branch context
- ✅ User confirmation workflow with clear activation details
- ✅ Integration with repository linking client
- ✅ Success confirmation and repository information display
- ✅ Error handling for activation failures
- ✅ Alias uniqueness validation across user repositories
- ✅ Comprehensive testing including failure scenarios
- ✅ User experience validation with clear communication
- ✅ Configuration options for auto-activation behavior