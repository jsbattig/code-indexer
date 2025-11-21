"""
Configuration Fixer

Intelligent validation and repair system for code-indexer configuration files.
Provides context-aware fixes based on actual file system state, git repository,
and Legacy collection contents.
"""

import json
import time
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from code_indexer.config import ConfigManager, Config
from code_indexer.services.json_validator import JSONSyntaxRepairer
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@dataclass
class ConfigFix:
    """Represents a configuration fix."""

    fix_type: str
    field: str
    description: str
    old_value: Any
    new_value: Any
    reason: str


@dataclass
class FixResult:
    """Result of configuration fixing operation."""

    success: bool
    fixes_applied: List[ConfigFix]
    errors: List[str]
    warnings: List[str]
    backup_created: Optional[str] = None


class GitStateDetector:
    """Detects git repository state from file system."""

    @staticmethod
    def detect_git_state(codebase_dir: Path) -> Dict[str, Any]:
        """Determine actual git state from repository."""
        try:
            # Check if we're in a git repository
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return {
                    "git_available": False,
                    "current_branch": "unknown",
                    "current_commit": "unknown",
                    "is_dirty": False,
                }

            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            current_branch = (
                branch_result.stdout.strip()
                if branch_result.returncode == 0
                else "unknown"
            )

            # Get current commit
            commit_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            current_commit = (
                commit_result.stdout.strip()
                if commit_result.returncode == 0
                else "unknown"
            )

            # Check if repository is dirty
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=codebase_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            is_dirty = (
                bool(status_result.stdout.strip())
                if status_result.returncode == 0
                else False
            )

            return {
                "git_available": True,
                "current_branch": current_branch,
                "current_commit": current_commit,
                "is_dirty": is_dirty,
            }

        except Exception as e:
            return {
                "git_available": False,
                "current_branch": "unknown",
                "current_commit": "unknown",
                "is_dirty": False,
                "error": str(e),
            }


class CollectionAnalyzer:
    """Analyzes Legacy collections to derive indexing statistics."""

    def __init__(self, vector_store_client: FilesystemVectorStore):
        self.vector_store_client = vector_store_client

    def derive_stats_from_collection(
        self, collection_name: str
    ) -> Optional[Dict[str, Any]]:
        """Derive accurate indexing statistics from Legacy collection."""
        try:
            # Check if collection exists
            if not self.vector_store_client.collection_exists(collection_name):
                return None

            # Get collection info
            collection_info = self.vector_store_client.get_collection_info(
                collection_name
            )
            points_count = collection_info.get("points_count", 0)

            if points_count == 0:
                return {
                    "files_processed": 0,
                    "chunks_indexed": 0,
                    "completed_files": [],
                    "files_to_index": [],
                    "status": "needs_indexing",
                }

            # For now, assume if there are points, there are some files processed
            # A more accurate implementation would query the collection for file metadata
            estimated_files = max(
                1, points_count // 10
            )  # Rough estimate: 10 chunks per file

            return {
                "files_processed": estimated_files,
                "chunks_indexed": points_count,
                "completed_files": [],  # Would need to query collection for actual file list
                "files_to_index": [],  # Empty since already indexed
                "status": "completed",
            }

        except Exception as e:
            print(f"Warning: Could not analyze collection {collection_name}: {e}")
            return None

    def find_wrong_collections(self, correct_project_name: str) -> List[str]:
        """Find collections that don't match the correct project name."""
        try:
            # For now, skip this check since we don't have a list collections method
            # This would need to be implemented in FilesystemVectorStore if needed
            print(
                "Note: Collection listing not implemented, skipping wrong collection detection"
            )
            return []

        except Exception as e:
            print(f"Warning: Could not check collections: {e}")
            return []


class FileSystemAnalyzer:
    """Analyzes project file system to determine indexable files."""

    @staticmethod
    def analyze_project_files(codebase_dir: Path, config: Config) -> Dict[str, Any]:
        """Analyze actual project files to determine what should be indexed."""
        try:
            from code_indexer.services.file_identifier import FileIdentifier

            file_identifier = FileIdentifier(codebase_dir, config)
            actual_files = file_identifier.get_current_files()

            return {
                "total_files_to_index": len(actual_files),
                "discovered_files": list(actual_files.keys()),
                "file_extensions_found": list(
                    set(
                        Path(f).suffix.lstrip(".")
                        for f in actual_files.keys()
                        if Path(f).suffix
                    )
                ),
            }

        except Exception as e:
            print(f"Warning: Could not analyze project files: {e}")
            return {
                "total_files_to_index": 0,
                "discovered_files": [],
                "file_extensions_found": [],
            }


class ConfigurationValidator:
    """Validates configuration for correctness and consistency."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self.metadata_file = config_dir / "metadata.json"

    def detect_correct_codebase_dir(self) -> Path:
        """Derive correct codebase_dir from config file location."""
        return self.config_dir.parent.absolute()

    def detect_correct_project_name(self) -> str:
        """Derive project name from directory structure."""
        return self.detect_correct_codebase_dir().name

    def validate_config(self, config: Config) -> List[ConfigFix]:
        """Validate configuration and suggest fixes."""
        fixes = []

        correct_codebase_dir = self.detect_correct_codebase_dir()

        # Check codebase_dir
        current_path_str = str(config.codebase_dir)
        correct_path_str = str(correct_codebase_dir)

        # Always fix tilde paths or paths that don't match exactly
        if current_path_str != correct_path_str or current_path_str.startswith("~"):
            # Handle tilde expansion for validation
            expanded_path = Path(current_path_str).expanduser().resolve()

            # Fix if path is wrong OR if it uses tilde (even if it expands correctly)
            if expanded_path != correct_codebase_dir or current_path_str.startswith(
                "~"
            ):
                reason = "Path should be parent directory of .code-indexer folder"
                if current_path_str.startswith("~"):
                    reason += " (converting tilde path to absolute path)"

                fixes.append(
                    ConfigFix(
                        fix_type="path_correction",
                        field="codebase_dir",
                        description="Fix codebase directory path",
                        old_value=current_path_str,
                        new_value=correct_path_str,
                        reason=reason,
                    )
                )

        # Validate that codebase_dir exists and is accessible
        if not correct_codebase_dir.exists():
            fixes.append(
                ConfigFix(
                    fix_type="path_missing",
                    field="codebase_dir",
                    description="Codebase directory does not exist",
                    old_value=str(config.codebase_dir),
                    new_value=str(correct_codebase_dir),
                    reason="Referenced directory is not accessible",
                )
            )

        return fixes

    def validate_metadata(
        self, metadata: Dict[str, Any], config: Config
    ) -> List[ConfigFix]:
        """Validate metadata and suggest fixes."""
        fixes = []

        correct_project_name = self.detect_correct_project_name()
        correct_codebase_dir = self.detect_correct_codebase_dir()

        # Check project_id
        if metadata.get("project_id") != correct_project_name:
            fixes.append(
                ConfigFix(
                    fix_type="project_name_correction",
                    field="project_id",
                    description="Fix project name",
                    old_value=metadata.get("project_id"),
                    new_value=correct_project_name,
                    reason=f"Project name should match directory name: {correct_project_name}",
                )
            )

        # Check git information
        git_state = GitStateDetector.detect_git_state(correct_codebase_dir)

        if metadata.get("git_available") != git_state["git_available"]:
            fixes.append(
                ConfigFix(
                    fix_type="git_availability_correction",
                    field="git_available",
                    description="Update git availability status",
                    old_value=metadata.get("git_available"),
                    new_value=git_state["git_available"],
                    reason="Git availability should reflect actual repository state",
                )
            )

        if git_state["git_available"]:
            if metadata.get("current_branch") != git_state["current_branch"]:
                fixes.append(
                    ConfigFix(
                        fix_type="git_branch_correction",
                        field="current_branch",
                        description="Update current branch",
                        old_value=metadata.get("current_branch"),
                        new_value=git_state["current_branch"],
                        reason="Branch should reflect actual git state",
                    )
                )

            if metadata.get("current_commit") != git_state["current_commit"]:
                fixes.append(
                    ConfigFix(
                        fix_type="git_commit_correction",
                        field="current_commit",
                        description="Update current commit",
                        old_value=metadata.get("current_commit"),
                        new_value=git_state["current_commit"],
                        reason="Commit should reflect actual git state",
                    )
                )

        # Check for invalid file paths (pointing to temp directories)
        files_to_index = metadata.get("files_to_index", [])
        invalid_files = [
            f for f in files_to_index if "/tmp/" in f or not Path(f).exists()
        ]

        if invalid_files:
            fixes.append(
                ConfigFix(
                    fix_type="invalid_file_paths",
                    field="files_to_index",
                    description="Remove invalid file paths",
                    old_value=len(files_to_index),
                    new_value=len(files_to_index) - len(invalid_files),
                    reason=f"Found {len(invalid_files)} invalid/non-existent file paths",
                )
            )

        return fixes


class ConfigurationRepairer:
    """Repairs configuration files using intelligent context-aware fixes."""

    def __init__(self, config_dir: Path, dry_run: bool = False):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self.metadata_file = config_dir / "metadata.json"
        self.dry_run = dry_run

        self.json_repairer = JSONSyntaxRepairer()
        self.validator = ConfigurationValidator(config_dir)

        # Initialize clients
        self.vector_store_client: Optional[FilesystemVectorStore] = None
        self.collection_analyzer: Optional[CollectionAnalyzer] = None

    def fix_configuration(self) -> FixResult:
        """Main entry point for fixing configuration."""
        all_fixes = []
        all_errors = []
        all_warnings: List[str] = []
        backup_files = []

        try:
            # Step 1: Fix JSON syntax errors first
            print("🔍 Checking JSON syntax...")
            json_results = self._fix_json_syntax()

            for filename, result in json_results.items():
                if result.get("success"):
                    if result.get("fixes_applied"):
                        print(f"  ✅ Fixed JSON syntax in {filename}")
                        if result.get("backup_created"):
                            backup_files.append(result["backup_created"])
                else:
                    all_errors.append(
                        f"JSON syntax error in {filename}: {result.get('message')}"
                    )
                    if result.get("manual_intervention_needed"):
                        return FixResult(
                            success=False,
                            fixes_applied=[],
                            errors=all_errors,
                            warnings=all_warnings,
                        )

            # Step 2: Load and validate configuration
            print("🔍 Validating configuration...")
            config_manager = ConfigManager(self.config_file)

            try:
                config = config_manager.load()
            except Exception as e:
                all_errors.append(f"Could not load configuration: {e}")
                return FixResult(
                    success=False,
                    fixes_applied=[],
                    errors=all_errors,
                    warnings=all_warnings,
                )

            # Step 3: Validate and fix config.json
            config_fixes = self.validator.validate_config(config)
            if config_fixes:
                print(f"  📝 Found {len(config_fixes)} configuration issues to fix")
                updated_config = self._apply_config_fixes(config, config_fixes)

                if not self.dry_run:
                    # Create backup
                    backup_path = self.config_file.with_suffix(".json.backup")
                    if self.config_file.exists():
                        backup_path.write_text(self.config_file.read_text())
                        backup_files.append(str(backup_path))

                    # Save updated config
                    config_manager._config = updated_config
                    config_manager.save()

                all_fixes.extend(config_fixes)

            # Determine if we're using filesystem backend (skip Legacy-specific operations)
            is_filesystem_backend = (
                config.vector_store and config.vector_store.provider == "filesystem"
            )

            # Step 4: Initialize Legacy client for metadata analysis (Legacy backend only)
            if not is_filesystem_backend:
                self._initialize_vector_store_client(config)

            # Step 5: Validate and fix metadata.json
            if self.metadata_file.exists():
                print("🔍 Validating metadata...")
                metadata_fixes = self._fix_metadata(config)
                all_fixes.extend(metadata_fixes)

                if metadata_fixes and not self.dry_run:
                    backup_path = self.metadata_file.with_suffix(".json.backup")
                    backup_path.write_text(self.metadata_file.read_text())
                    backup_files.append(str(backup_path))

            # Step 6: Check and fix CoW symlink issues (Legacy backend only)
            if not is_filesystem_backend:
                print("🔍 Checking CoW symlinks...")
                cow_fixes = self._fix_cow_symlinks()
                all_fixes.extend(cow_fixes)

            # Step 6.5: Check and fix project configuration (Legacy backend only)
            # This is handled by conditional logic inside _fix_project_configuration
            print("🔍 Checking project configuration...")
            project_fixes = self._fix_project_configuration()
            all_fixes.extend(project_fixes)

            # Step 7: Check for wrong collections (Legacy backend only)
            if not is_filesystem_backend:
                print("🔍 Checking Legacy collections...")
                collection_warnings = self._check_collections()
                all_warnings.extend(collection_warnings)

            print("✅ Configuration analysis complete")
            print(f"   Applied {len(all_fixes)} fixes")
            print(f"   Found {len(all_warnings)} warnings")

            return FixResult(
                success=True,
                fixes_applied=all_fixes,
                errors=all_errors,
                warnings=all_warnings,
                backup_created=backup_files[0] if backup_files else None,
            )

        except Exception as e:
            all_errors.append(f"Unexpected error during configuration fix: {e}")
            return FixResult(
                success=False,
                fixes_applied=all_fixes,
                errors=all_errors,
                warnings=all_warnings,
            )

    def _fix_json_syntax(self) -> Dict[str, Dict[str, Any]]:
        """Fix JSON syntax errors in both config files."""
        results = {}

        # Check config.json
        if self.config_file.exists():
            results["config.json"] = self.json_repairer.repair_json_file(
                self.config_file, dry_run=self.dry_run
            )

        # Check metadata.json
        if self.metadata_file.exists():
            results["metadata.json"] = self.json_repairer.repair_json_file(
                self.metadata_file, dry_run=self.dry_run
            )

        return results

    def _apply_config_fixes(self, config: Config, fixes: List[ConfigFix]) -> Config:
        """Apply fixes to configuration object."""
        for fix in fixes:
            if fix.field == "codebase_dir":
                config.codebase_dir = Path(fix.new_value)

        return config

    def _fix_metadata(self, config: Config) -> List[ConfigFix]:
        """Fix metadata.json file."""
        try:
            with open(self.metadata_file, "r") as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load metadata.json: {e}")
            return []

        fixes = self.validator.validate_metadata(metadata, config)

        if fixes and not self.dry_run:
            # Apply fixes to metadata
            corrected_metadata = self._apply_metadata_fixes(metadata, fixes, config)

            # Write updated metadata
            with open(self.metadata_file, "w") as f:
                json.dump(corrected_metadata, f, indent=2)

        return fixes

    def _apply_metadata_fixes(
        self, metadata: Dict[str, Any], fixes: List[ConfigFix], config: Config
    ) -> Dict[str, Any]:
        """Apply fixes to metadata."""
        correct_project_name = self.validator.detect_correct_project_name()
        correct_codebase_dir = self.validator.detect_correct_codebase_dir()

        # Get git state
        git_state = GitStateDetector.detect_git_state(correct_codebase_dir)

        # Try to get collection stats
        collection_stats = None
        if self.collection_analyzer:
            # Collection name is the model name (filesystem-safe)
            if config.embedding_provider == "voyage-ai":
                model_name = config.voyage_ai.model
            else:
                model_name = "unknown"

            # Make filesystem-safe (matching FilesystemVectorStore.resolve_collection_name)
            collection_name = model_name.replace("/", "_").replace(":", "_")
            collection_stats = self.collection_analyzer.derive_stats_from_collection(
                collection_name
            )

        # If no collection stats, use minimal placeholder without expensive file scanning
        # NOTE: Config fixing should NOT require analyzing every file in repository
        # Metadata will be rebuilt on next index operation
        if not collection_stats:
            collection_stats = {
                "files_processed": 0,
                "chunks_indexed": 0,
                "completed_files": [],
                "files_to_index": [],  # Empty - no need to scan filesystem
                "total_files_to_index": 0,  # Zero - will be populated on next index operation
                "status": "needs_indexing",
            }

        # Build corrected metadata
        corrected_metadata = {
            **metadata,  # Keep existing values as base
            "project_id": correct_project_name,
            "git_available": git_state["git_available"],
            "current_branch": git_state["current_branch"],
            "current_commit": git_state["current_commit"],
            "embedding_provider": config.embedding_provider,
            **collection_stats,
            "last_index_timestamp": time.time(),
            "indexed_at": datetime.now().isoformat(),
        }

        return corrected_metadata

    def _initialize_vector_store_client(self, config: Config):
        """Initialize vector store client for collection analysis.

        Note: Method name retained for backward compatibility but now initializes FilesystemVectorStore (Story #505).
        """
        try:
            index_dir = Path(config.codebase_dir) / ".code-indexer" / "index"
            self.vector_store_client = FilesystemVectorStore(
                base_path=index_dir, project_root=Path(config.codebase_dir)
            )
            if self.vector_store_client.health_check():
                self.collection_analyzer = CollectionAnalyzer(self.vector_store_client)
            else:
                print("Warning: Vector store not accessible for collection analysis")
        except Exception as e:
            print(f"Warning: Could not initialize vector store: {e}")

    def _check_collections(self) -> List[str]:
        """Check for collections with wrong names."""
        warnings: List[str] = []

        if not self.collection_analyzer:
            return warnings

        correct_project_name = self.validator.detect_correct_project_name()
        wrong_collections = self.collection_analyzer.find_wrong_collections(
            correct_project_name
        )

        for collection in wrong_collections:
            warnings.append(
                f"Found collection '{collection}' that doesn't match project name '{correct_project_name}'. "
                f"Consider running 'cidx clean-data --all-projects' to clean up."
            )

        return warnings

    def _fix_cow_symlinks(self) -> List[ConfigFix]:
        """Check and fix CoW (Copy-on-Write) symlink issues."""
        fixes = []

        try:
            # Check for stale symlinks in global collections directory
            global_collections_dir = Path.home() / "..collections"

            if global_collections_dir.exists():
                stale_symlinks = []

                for item in global_collections_dir.iterdir():
                    if item.is_symlink():
                        target = item.resolve()
                        # Check if target exists and if it's pointing to correct project
                        if not target.exists() or not str(target).startswith(
                            str(self.config_dir.parent)
                        ):
                            stale_symlinks.append(item)

                if stale_symlinks:
                    fixes.append(
                        ConfigFix(
                            fix_type="cow_symlink_cleanup",
                            field="symlinks",
                            description="Remove stale CoW symlinks",
                            old_value=len(stale_symlinks),
                            new_value=0,
                            reason=f"Found {len(stale_symlinks)} stale symlinks pointing to wrong locations",
                        )
                    )

                    if not self.dry_run:
                        for symlink in stale_symlinks:
                            print(f"  🗑️  Removing stale symlink: {symlink.name}")
                            symlink.unlink()

            # Check for orphaned collection directories in project
            project_collections_dir = self.config_dir / ".collection"

            if project_collections_dir.exists():
                orphaned_dirs = []

                for item in project_collections_dir.iterdir():
                    if item.is_dir():
                        # Check if corresponding symlink exists
                        expected_symlink = global_collections_dir / item.name
                        if (
                            not expected_symlink.exists()
                            or not expected_symlink.is_symlink()
                        ):
                            orphaned_dirs.append(item)

                if orphaned_dirs:
                    fixes.append(
                        ConfigFix(
                            fix_type="cow_orphaned_directories",
                            field="directories",
                            description="Remove orphaned collection directories",
                            old_value=len(orphaned_dirs),
                            new_value=0,
                            reason=f"Found {len(orphaned_dirs)} orphaned collection directories without symlinks",
                        )
                    )

                    if not self.dry_run:
                        for orphaned_dir in orphaned_dirs:
                            print(
                                f"  🗑️  Removing orphaned directory: {orphaned_dir.name}"
                            )
                            shutil.rmtree(orphaned_dir, ignore_errors=True)

            # Ensure proper directory structure exists
            if not global_collections_dir.exists():
                fixes.append(
                    ConfigFix(
                        fix_type="cow_directory_structure",
                        field="directories",
                        description="Create CoW directory structure",
                        old_value="missing",
                        new_value="created",
                        reason="Global collections directory is required for CoW functionality",
                    )
                )

                if not self.dry_run:
                    print(
                        f"  📁 Creating global collections directory: {global_collections_dir}"
                    )
                    global_collections_dir.mkdir(parents=True, exist_ok=True)

            # Ensure project collection directory exists
            if not project_collections_dir.exists():
                fixes.append(
                    ConfigFix(
                        fix_type="cow_project_structure",
                        field="directories",
                        description="Create project CoW directory structure",
                        old_value="missing",
                        new_value="created",
                        reason="Project collections directory is required for CoW functionality",
                    )
                )

                if not self.dry_run:
                    print(
                        f"  📁 Creating project collections directory: {project_collections_dir}"
                    )
                    project_collections_dir.mkdir(parents=True, exist_ok=True)

            # Create expected collection structure for current project
            try:
                # Load config to get embedding provider details
                config_manager = ConfigManager(self.config_file)
                config = config_manager.load()

                # Load metadata to get project details
                if self.metadata_file.exists():
                    with open(self.metadata_file, "r") as f:
                        metadata = json.load(f)

                    embedding_provider = metadata.get(
                        "embedding_provider", config.embedding_provider
                    )

                    # Get model name from config based on provider
                    if embedding_provider == "voyage-ai":
                        model_name = config.voyage_ai.model
                    else:
                        model_name = "unknown"

                    # Collection name is the model name (filesystem-safe)
                    # Matches FilesystemVectorStore.resolve_collection_name
                    expected_collection_name = model_name.replace("/", "_").replace(
                        ":", "_"
                    )

                    expected_local_dir = (
                        project_collections_dir / expected_collection_name
                    )
                    expected_symlink = global_collections_dir / expected_collection_name

                    # Check if the expected structure exists
                    if not expected_local_dir.exists() or not expected_symlink.exists():
                        fixes.append(
                            ConfigFix(
                                fix_type="cow_expected_structure",
                                field="collection_structure",
                                description="Create expected CoW collection structure",
                                old_value="missing",
                                new_value=expected_collection_name,
                                reason=f"Collection structure needed for project with {embedding_provider}",
                            )
                        )

                        if not self.dry_run:
                            print(
                                f"  📁 Creating expected collection directory: {expected_collection_name}"
                            )
                            expected_local_dir.mkdir(parents=True, exist_ok=True)

                            if (
                                expected_symlink.exists()
                                or expected_symlink.is_symlink()
                            ):
                                if expected_symlink.is_symlink():
                                    expected_symlink.unlink()
                                else:
                                    shutil.rmtree(expected_symlink, ignore_errors=True)

                            print(f"  🔗 Creating symlink: {expected_collection_name}")
                            expected_symlink.symlink_to(
                                expected_local_dir, target_is_directory=True
                            )

            except Exception as e:
                print(f"Warning: Could not create expected collection structure: {e}")

        except Exception as e:
            print(f"Warning: Could not check CoW symlinks: {e}")

        return fixes

    def _regenerate_project_configuration(self) -> Dict[str, Any]:
        """Regenerate project configuration (deprecated - containers no longer used).

        Container management is deprecated (Story #506). This method returns empty
        configuration to maintain compatibility while removal is in progress.
        """
        print(
            "Info: Project configuration regeneration skipped (container management deprecated)"
        )
        return {}

    def _regenerate_port_assignments(self, project_hash: str) -> Dict[str, int]:
        """Port assignment regeneration (deprecated - containers no longer used)."""
        print(
            "Info: Port assignment regeneration skipped (container management deprecated)"
        )
        return {}

    def _regenerate_container_names(self, project_root: Path) -> Dict[str, str]:
        """Container name regeneration (deprecated - containers no longer used)."""
        print(
            "Info: Container name regeneration skipped (container management deprecated)"
        )
        return {}

    def _clear_stale_container_references(
        self, config: Config, project_info: Dict[str, Any]
    ) -> List[ConfigFix]:
        """Clear stale container references from configuration."""
        fixes = []

        try:
            # Check if project configuration needs updating
            if hasattr(config, "project_ports"):
                current_ports = config.project_ports
                new_ports = project_info.get("port_assignments", {})

                # Compare current ports with calculated ports
                ports_need_update = False
                for service, new_port in new_ports.items():
                    current_port = getattr(current_ports, service, 0)
                    if current_port != new_port:
                        ports_need_update = True
                        break

                if ports_need_update:
                    fixes.append(
                        ConfigFix(
                            fix_type="port_regeneration",
                            field="project_ports",
                            description="Regenerate port assignments for CoW clone",
                            old_value=str(current_ports),
                            new_value=str(new_ports),
                            reason="CoW clone needs unique ports based on filesystem location",
                        )
                    )

            # Check container names if they exist in config
            container_names = project_info.get("container_names", {})
            if container_names:
                fixes.append(
                    ConfigFix(
                        fix_type="container_name_regeneration",
                        field="container_names",
                        description="Regenerate container names for CoW clone",
                        old_value="stale_references",
                        new_value=str(container_names),
                        reason="CoW clone needs unique container names based on filesystem location",
                    )
                )

        except Exception as e:
            print(f"Warning: Could not clear stale container references: {e}")

        return fixes

    def _fix_project_configuration(self) -> List[ConfigFix]:
        """Fix project configuration for CoW clones (project hash, ports, container names).

        Only applies to Legacy backend. Filesystem backend doesn't need container/port configuration.
        """
        fixes: List[ConfigFix] = []

        try:
            # Load current configuration
            config_manager = ConfigManager(self.config_file)
            config = config_manager.load()

            # Skip Legacy-specific configuration if using filesystem backend
            if config.vector_store and config.vector_store.provider == "filesystem":
                print(
                    "  ℹ️  Skipping Legacy container/port configuration (filesystem backend)"
                )
                return fixes

            # Regenerate project configuration based on current filesystem location
            project_info = self._regenerate_project_configuration()

            if not project_info:
                return fixes

            # Clear stale container references
            container_fixes = self._clear_stale_container_references(
                config, project_info
            )
            fixes.extend(container_fixes)

            # Apply the fixes if not in dry run mode
            if fixes and not self.dry_run:
                updated_config = self._apply_project_config_fixes(config, project_info)
                config_manager._config = updated_config
                config_manager.save()

        except Exception as e:
            print(f"Warning: Could not fix project configuration: {e}")

        return fixes

    def _apply_project_config_fixes(
        self, config: Config, project_info: Dict[str, Any]
    ) -> Config:
        """Apply project configuration fixes to the config object."""
        try:
            # Update port assignments - CRITICAL: Ensure ALL required ports exist
            new_ports = project_info.get("port_assignments", {})
            if new_ports and hasattr(config, "project_ports"):
                # FIXED: Always set ALL required ports, don't check if they exist first
                # This ensures CoW clones get complete port regeneration
                # Note: secondary_port is only required for secondary embedding provider
                ALWAYS_REQUIRED_PORTS = ["service_port", "data_cleaner_port"]
                CONDITIONAL_PORTS = [
                    "secondary_port"
                ]  # Only needed for secondary provider

                for port_name in ALWAYS_REQUIRED_PORTS:
                    if port_name in new_ports:
                        setattr(config.project_ports, port_name, new_ports[port_name])
                    else:
                        raise ValueError(
                            f"CRITICAL: {port_name} missing from regenerated ports. "
                            f"Available ports: {list(new_ports.keys())}"
                        )

                # Handle conditional ports (only set if they exist in new_ports)
                for port_name in CONDITIONAL_PORTS:
                    if port_name in new_ports:
                        setattr(config.project_ports, port_name, new_ports[port_name])

            # Update container names - CRITICAL: Ensure ALL required container names exist
            container_names = project_info.get("container_names", {})
            if container_names and hasattr(config, "project_containers"):
                # FIXED: Always set ALL required container names, don't check conditionally
                # Note: secondary_name is only required for secondary embedding provider
                ALWAYS_REQUIRED_CONTAINERS = [
                    "project_hash",
                    "service_name",
                    "data_cleaner_name",
                ]
                CONDITIONAL_CONTAINERS = [
                    "secondary_name"
                ]  # Only needed for secondary provider

                for container_field in ALWAYS_REQUIRED_CONTAINERS:
                    if container_field in container_names:
                        setattr(
                            config.project_containers,
                            container_field,
                            container_names[container_field],
                        )
                    else:
                        raise ValueError(
                            f"CRITICAL: {container_field} missing from regenerated containers. "
                            f"Available containers: {list(container_names.keys())}"
                        )

                # Handle conditional containers (only set if they exist in container_names)
                for container_field in CONDITIONAL_CONTAINERS:
                    if container_field in container_names:
                        setattr(
                            config.project_containers,
                            container_field,
                            container_names[container_field],
                        )

        except Exception as e:
            print(f"Warning: Could not apply project config fixes: {e}")

        return config


def generate_fix_report(result: FixResult, dry_run: bool = False) -> str:
    """Generate a user-friendly report of fixes applied."""
    lines = []

    action = "Would apply" if dry_run else "Applied"

    if result.success:
        lines.append(
            f"✅ Configuration fix {'simulation' if dry_run else 'completed'} successfully"
        )

        if result.fixes_applied:
            lines.append(f"\n📝 {action} {len(result.fixes_applied)} fixes:")

            # Group fixes by type
            fix_groups: Dict[str, List[ConfigFix]] = {}
            for fix in result.fixes_applied:
                fix_type = fix.fix_type
                if fix_type not in fix_groups:
                    fix_groups[fix_type] = []
                fix_groups[fix_type].append(fix)

            for fix_type, fixes in fix_groups.items():
                lines.append(f"\n  📌 {fix_type.replace('_', ' ').title()}:")
                for fix in fixes:
                    lines.append(f"    • {fix.description}")
                    if fix.old_value != fix.new_value:
                        lines.append(f"      Old: {fix.old_value}")
                        lines.append(f"      New: {fix.new_value}")
        else:
            lines.append("\n✨ No configuration issues found!")

        if result.warnings:
            lines.append(f"\n⚠️ {len(result.warnings)} warnings:")
            for warning in result.warnings:
                lines.append(f"  • {warning}")

        if result.backup_created and not dry_run:
            lines.append(f"\n💾 Backup created: {result.backup_created}")

    else:
        lines.append("❌ Configuration fix failed")

        if result.errors:
            lines.append("\n🚨 Errors:")
            for error in result.errors:
                lines.append(f"  • {error}")

    return "\n".join(lines)
