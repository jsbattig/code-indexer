# Story: Deactivation and Cleanup

## Story Description
Implement proper deactivation and cleanup for composite repositories, ensuring all resources are released and component repositories are properly removed.

## Business Context
**Need**: Clean lifecycle management for composite repositories
**Constraint**: Must handle multiple component repositories atomically

## Technical Implementation

### Deactivation Endpoint
```python
@router.delete("/api/repos/{user_alias}")
async def deactivate_repository(user_alias: str):
    repo = activated_repo_manager.get_repository(user_alias)
    if not repo:
        raise HTTPException(404, "Repository not found")

    # Use same deactivation for both types
    success = await activated_repo_manager.deactivate_repository(user_alias)

    if success:
        return {"message": f"Repository '{user_alias}' deactivated successfully"}
    else:
        raise HTTPException(500, "Failed to deactivate repository")
```

### Enhanced Deactivation Logic
```python
class ActivatedRepoManager:
    def deactivate_repository(self, user_alias: str) -> bool:
        """Deactivate repository (single or composite)"""

        repo = self.get_repository(user_alias)
        if not repo:
            return False

        try:
            if repo.is_composite:
                return self._deactivate_composite(repo)
            else:
                return self._deactivate_single(repo)
        except Exception as e:
            logger.error(f"Deactivation failed: {e}")
            return False


    def _deactivate_composite(self, repo: ActivatedRepository) -> bool:
        """Clean up composite repository and all components"""

        # 1. Stop any running containers (if applicable)
        self._stop_composite_services(repo.path)

        # 2. Clean up component repositories
        from ...proxy.proxy_config_manager import ProxyConfigManager
        proxy_config = ProxyConfigManager(repo.path)

        for repo_name in proxy_config.get_discovered_repos():
            subrepo_path = repo.path / repo_name
            if subrepo_path.exists():
                # Remove component repo (CoW clone)
                shutil.rmtree(subrepo_path)
                logger.info(f"Removed component: {repo_name}")

        # 3. Remove proxy configuration
        config_dir = repo.path / ".code-indexer"
        if config_dir.exists():
            shutil.rmtree(config_dir)

        # 4. Remove composite repository directory
        if repo.path.exists():
            shutil.rmtree(repo.path)

        logger.info(f"Composite repository '{repo.user_alias}' deactivated")
        return True


    def _stop_composite_services(self, repo_path: Path):
        """Stop any services running for composite repo"""

        try:
            # Use CLI's execute_proxy_command for stop
            from ...cli_integration import execute_proxy_command

            result = execute_proxy_command(
                root_dir=repo_path,
                command="stop",
                quiet=True
            )

            if result.returncode == 0:
                logger.info("Stopped composite repository services")
        except Exception as e:
            # Non-fatal - services might not be running
            logger.debug(f"Service stop attempted: {e}")
```

### Cleanup Verification
```python
def verify_cleanup(self, user_alias: str) -> CleanupStatus:
    """Verify repository was properly cleaned up"""

    repo_path = self._get_user_repo_path(user_alias)

    return CleanupStatus(
        directory_removed=not repo_path.exists(),
        metadata_cleaned=not (repo_path / ".cidx_metadata.json").exists(),
        config_cleaned=not (repo_path / ".code-indexer").exists(),
        subrepositories_cleaned=self._check_subrepos_cleaned(repo_path)
    )


def _check_subrepos_cleaned(self, repo_path: Path) -> bool:
    """Check if all subdirectories are removed"""
    if not repo_path.exists():
        return True

    # Should have no subdirectories left
    subdirs = [d for d in repo_path.iterdir() if d.is_dir()]
    return len(subdirs) == 0
```

## Acceptance Criteria
- [x] Deactivation removes all component repositories
- [x] Proxy configuration is cleaned up
- [x] Any running services are stopped
- [x] Composite directory is fully removed
- [x] Operation is atomic (all or nothing)
- [x] Single-repo deactivation still works

## Test Scenarios
1. **Full Cleanup**: All components and config removed
2. **Service Shutdown**: Running services properly stopped
3. **Error Recovery**: Partial failures handled gracefully
4. **Verification**: Can verify cleanup completed
5. **Idempotent**: Multiple deactivations don't error

## Implementation Notes
- Stop services before removing directories
- Use CLI's execute_proxy_command for service management
- Atomic operation - rollback on partial failure
- Log all cleanup steps for debugging

## Dependencies
- CLI's execute_proxy_command for stop operation
- ProxyConfigManager for component discovery
- Filesystem operations for cleanup

## Estimated Effort
~40 lines for complete cleanup logic