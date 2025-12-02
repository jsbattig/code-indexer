"""
Global Activator for orchestrating automatic global activation.

Coordinates alias creation and registry updates when a golden repo
is registered, implementing the automatic activation workflow.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Union

from .alias_manager import AliasManager
from .global_registry import GlobalRegistry


logger = logging.getLogger(__name__)


class GlobalActivationError(Exception):
    """Exception raised when global activation fails."""

    pass


class GlobalActivator:
    """
    Orchestrates automatic global activation of golden repositories.

    Handles the complete workflow of creating aliases and updating
    the global registry when a golden repo is registered.
    """

    def __init__(self, golden_repos_dir: str):
        """
        Initialize the global activator.

        Args:
            golden_repos_dir: Path to golden repos directory
        """
        self.golden_repos_dir = Path(golden_repos_dir)

        # Initialize components
        aliases_dir = self.golden_repos_dir / "aliases"
        self.alias_manager = AliasManager(str(aliases_dir))
        self.registry = GlobalRegistry(str(self.golden_repos_dir))

    def activate_golden_repo(
        self,
        repo_name: str,
        repo_url: str,
        clone_path: str,
        enable_temporal: bool = False,
        temporal_options: Optional[Dict[str, Union[int, str]]] = None,
    ) -> None:
        """
        Activate a golden repository globally.

        Creates an alias and registers the repo in the global registry.
        Uses {repo-name}-global naming convention for aliases.

        Args:
            repo_name: Repository name (e.g., "my-repo")
            repo_url: Git repository URL
            clone_path: Path to the cloned/indexed repository
            enable_temporal: Whether to enable temporal indexing (git history search)
            temporal_options: Temporal indexing options (max_commits, since_date, diff_context)

        Raises:
            GlobalActivationError: If activation fails
        """
        alias_name = f"{repo_name}-global"

        try:
            # Step 1: Create alias pointer file (atomically)
            logger.info(f"Creating global alias: {alias_name}")
            self.alias_manager.create_alias(
                alias_name=alias_name, target_path=clone_path, repo_name=repo_name
            )

            # Step 2: Register in global registry (atomically)
            # Include temporal settings for RefreshScheduler to use (Story #527)
            logger.info(f"Registering in global registry: {alias_name}")
            self.registry.register_global_repo(
                repo_name=repo_name,
                alias_name=alias_name,
                repo_url=repo_url,
                index_path=clone_path,
                enable_temporal=enable_temporal,
                temporal_options=temporal_options,
            )

            # Step 3: Generate meta-directory description file (Story #523)
            self._generate_meta_description_file(repo_name, repo_url, clone_path)

            logger.info(f"Global activation complete: {alias_name}")

        except Exception as e:
            # Clean up partial state on failure
            error_msg = f"Global activation failed for {repo_name}: {e}"
            logger.error(error_msg)

            # Attempt cleanup of any partial state
            try:
                if self.alias_manager.alias_exists(alias_name):
                    logger.warning(f"Cleaning up alias after failure: {alias_name}")
                    self.alias_manager.delete_alias(alias_name)

                if self.registry.get_global_repo(alias_name):
                    logger.warning(
                        f"Cleaning up registry entry after failure: {alias_name}"
                    )
                    self.registry.unregister_global_repo(alias_name)

            except Exception as cleanup_error:
                logger.error(f"Cleanup failed after activation error: {cleanup_error}")

            # Re-raise as GlobalActivationError
            raise GlobalActivationError(error_msg) from e

    def deactivate_golden_repo(self, repo_name: str) -> None:
        """
        Deactivate a golden repository globally.

        Removes the alias, unregisters from the global registry, and cleans up
        the meta-directory description file.

        Args:
            repo_name: Repository name

        Raises:
            GlobalActivationError: If deactivation fails
        """
        alias_name = f"{repo_name}-global"

        try:
            # Remove from registry
            self.registry.unregister_global_repo(alias_name)

            # Remove alias
            self.alias_manager.delete_alias(alias_name)

            # Remove meta-directory description file (Story #532)
            # File name is {repo_name}.md (NOT {alias_name}.md)
            self._cleanup_meta_description_file(repo_name)

            logger.info(f"Global deactivation complete: {alias_name}")

        except Exception as e:
            error_msg = f"Global deactivation failed for {repo_name}: {e}"
            logger.error(error_msg)
            raise GlobalActivationError(error_msg) from e

    def _cleanup_meta_description_file(self, repo_name: str) -> None:
        """
        Clean up meta-directory description file for a removed repository.

        Also triggers re-indexing of the meta-directory if it exists and
        has been initialized with cidx.

        Args:
            repo_name: Repository name (used for .md filename)
        """
        import subprocess

        meta_dir = self.golden_repos_dir / "cidx-meta"

        # Delete the description file if it exists
        meta_description_file = meta_dir / f"{repo_name}.md"
        if meta_description_file.exists():
            try:
                meta_description_file.unlink()
                logger.info(
                    f"Deleted meta-directory description file: {meta_description_file}"
                )
            except OSError as e:
                # Log but don't fail - file cleanup is best-effort
                logger.warning(
                    f"Failed to delete meta-directory description file "
                    f"{meta_description_file}: {e}"
                )
        else:
            logger.debug(
                f"Meta-directory description file does not exist: {meta_description_file}"
            )

        # Re-index the meta-directory if it exists and has been initialized
        if meta_dir.exists() and (meta_dir / ".code-indexer").exists():
            try:
                result = subprocess.run(
                    ["cidx", "index"],
                    cwd=str(meta_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,  # 1 minute timeout for meta-directory re-indexing
                )
                if result.returncode == 0:
                    logger.info(f"Re-indexed meta-directory: {meta_dir}")
                else:
                    # Log but don't fail - re-indexing is best-effort
                    logger.warning(
                        f"Meta-directory re-indexing returned non-zero: "
                        f"exit code {result.returncode}, stderr: {result.stderr}"
                    )
            except subprocess.TimeoutExpired:
                logger.warning(f"Meta-directory re-indexing timed out: {meta_dir}")
            except FileNotFoundError:
                logger.warning("cidx command not found for meta-directory re-indexing")
            except Exception as e:
                logger.warning(f"Meta-directory re-indexing failed: {e}")

    def _generate_meta_description_file(
        self, repo_name: str, repo_url: str, clone_path: str
    ) -> None:
        """
        Generate meta-directory description file for a newly activated repository.

        Uses AI-powered analysis (Claude CLI) to generate comprehensive metadata.

        Args:
            repo_name: Repository name (used for .md filename)
            repo_url: Git repository URL
            clone_path: Path to the cloned repository
        """
        import subprocess

        from .description_generator import DescriptionGenerator
        from .repo_analyzer import RepoAnalyzer

        meta_dir = self.golden_repos_dir / "cidx-meta"

        try:
            # Ensure meta-directory exists
            meta_dir.mkdir(parents=True, exist_ok=True)

            # Analyze repository with Claude CLI (or fallback to static)
            analyzer = RepoAnalyzer(clone_path)
            info = analyzer.extract_info()

            # Generate description file
            generator = DescriptionGenerator(str(meta_dir))
            generator.create_description(
                repo_name=repo_name,
                repo_url=repo_url,
                description=info.summary,
                technologies=info.technologies,
                purpose=info.purpose,
                features=info.features,
                use_cases=info.use_cases,
            )

            logger.info(f"Generated meta-directory description: {repo_name}.md")

            # Initialize meta-directory if needed
            if not (meta_dir / ".code-indexer").exists():
                try:
                    init_result = subprocess.run(
                        ["cidx", "init"],
                        cwd=str(meta_dir),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if init_result.returncode == 0:
                        logger.info(f"Initialized meta-directory: {meta_dir}")
                    else:
                        logger.warning(
                            f"Meta-directory initialization failed: {init_result.stderr}"
                        )
                        return  # Can't index if init failed
                except Exception as e:
                    logger.warning(f"Meta-directory initialization failed: {e}")
                    return

            # Re-index meta-directory (always, since we created or already have .code-indexer)
            try:
                result = subprocess.run(
                    ["cidx", "index"],
                    cwd=str(meta_dir),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    logger.info(f"Re-indexed meta-directory: {meta_dir}")
                else:
                    logger.warning(
                        f"Meta-directory re-indexing returned non-zero: {result.stderr}"
                    )
            except Exception as e:
                logger.warning(f"Meta-directory re-indexing failed: {e}")

        except Exception as e:
            # Log but don't fail activation - description generation is best-effort
            logger.warning(
                f"Failed to generate meta-directory description for {repo_name}: {e}"
            )

    def is_globally_active(self, repo_name: str) -> bool:
        """
        Check if a repository is globally active.

        Args:
            repo_name: Repository name

        Returns:
            True if globally active, False otherwise
        """
        alias_name = f"{repo_name}-global"
        return self.registry.get_global_repo(alias_name) is not None

    def get_global_alias_name(self, repo_name: str) -> str:
        """
        Get the global alias name for a repository.

        Args:
            repo_name: Repository name

        Returns:
            Global alias name (e.g., "my-repo-global")
        """
        return f"{repo_name}-global"
