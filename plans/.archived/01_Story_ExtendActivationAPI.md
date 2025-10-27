# Story: Extend Activation API

## Story Description
Modify the repository activation API endpoint to accept an optional array of golden repository aliases, enabling composite repository creation.

## Business Context
**Requirement**: "Activation of composite activated repo" [Phase 2]
**Constraint**: "Commands limited to what's already supported within cidx for composite repos" [Phase 1]

## Technical Implementation

### API Model Extension
```python
class ActivateRepositoryRequest(BaseModel):
    golden_repo_alias: Optional[str] = None        # Existing
    golden_repo_aliases: Optional[List[str]] = None  # NEW
    user_alias: Optional[str] = None

    @validator('golden_repo_aliases')
    def validate_aliases(cls, v, values):
        if v and values.get('golden_repo_alias'):
            raise ValueError("Cannot specify both golden_repo_alias and golden_repo_aliases")
        if v and len(v) < 2:
            raise ValueError("Composite activation requires at least 2 repositories")
        return v
```

### Endpoint Handler Update
```python
@router.post("/api/repos/activate", response_model=ActivateRepositoryResponse)
async def activate_repository(request: ActivateRepositoryRequest):
    if request.golden_repo_aliases:
        # Route to composite activation
        result = await activated_repo_manager.activate_repository(
            golden_repo_aliases=request.golden_repo_aliases,
            user_alias=request.user_alias
        )
    else:
        # Existing single-repo logic
        result = await activated_repo_manager.activate_repository(
            golden_repo_alias=request.golden_repo_alias,
            user_alias=request.user_alias
        )
```

### Manager Method Signature
```python
class ActivatedRepoManager:
    def activate_repository(
        self,
        golden_repo_alias: Optional[str] = None,
        golden_repo_aliases: Optional[List[str]] = None,  # NEW
        user_alias: Optional[str] = None
    ) -> ActivatedRepository:
        # Validation
        if golden_repo_aliases and golden_repo_alias:
            raise ValueError("Cannot specify both parameters")

        if golden_repo_aliases:
            return self._do_activate_composite_repository(
                golden_repo_aliases, user_alias
            )

        # Existing single-repo logic unchanged
        return self._do_activate_repository(golden_repo_alias, user_alias)
```

## Acceptance Criteria
- [x] API accepts new `golden_repo_aliases` parameter
- [x] Validates mutual exclusivity with `golden_repo_alias`
- [x] Requires minimum 2 repositories for composite
- [x] Routes to appropriate activation method
- [x] Returns proper response for both single and composite repos
- [x] Existing single-repo activation remains unchanged

## Test Scenarios
1. **Happy Path**: Activate with 3 valid golden repo aliases
2. **Validation**: Reject if both single and array parameters provided
3. **Validation**: Reject if array has less than 2 repositories
4. **Validation**: Reject if any golden repo alias doesn't exist
5. **Backward Compatibility**: Single-repo activation still works

## Implementation Notes
- Maintain backward compatibility with existing single-repo activation
- Use same response model for both single and composite
- Composite activation delegates to new internal method
- Validation happens at both API and manager levels

## Dependencies
- Existing ActivatedRepoManager
- Existing golden repository validation logic

## Estimated Effort
~30 lines of code for API extension and validation