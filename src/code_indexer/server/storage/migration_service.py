"""
Migration service for legacy JSON to SQLite migration.

Story #702: Migrate Central JSON Files to SQLite

Provides one-time migration of legacy JSON files to SQLite database,
with idempotency support for safe re-runs.
"""

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict

from .sqlite_backends import (
    GlobalReposSqliteBackend,
    UsersSqliteBackend,
    SyncJobsSqliteBackend,
    CITokensSqliteBackend,
    SessionsSqliteBackend,
    SSHKeysSqliteBackend,
    GoldenRepoMetadataSqliteBackend,
)

logger = logging.getLogger(__name__)


class MigrationService:
    """
    Service for migrating legacy JSON files to SQLite.

    Handles migration of:
    - global_registry.json -> global_repos table
    - users.json -> users, user_api_keys, user_mcp_credentials tables

    Migration is idempotent - safe to run multiple times.
    """

    def __init__(self, source_dir: str, db_path: str) -> None:
        """
        Initialize the migration service.

        Args:
            source_dir: Directory containing legacy JSON files.
            db_path: Path to target SQLite database.
        """
        self.source_dir = source_dir
        self.db_path = db_path

    def is_migration_needed(self) -> bool:
        """
        Check if migration is needed.

        Returns:
            True if legacy JSON files exist, False otherwise.
        """
        source_path = Path(self.source_dir)
        json_files = [
            "global_registry.json",
            "users.json",
            "jobs.json",
            "ci_tokens.json",
            "invalidated_sessions.json",
        ]

        for json_file in json_files:
            if (source_path / json_file).exists():
                return True

        # Check for SSH keys directory with JSON files
        ssh_keys_dir = source_path / "ssh_keys"
        if ssh_keys_dir.exists() and list(ssh_keys_dir.glob("*.json")):
            return True

        return False

    def migrate_global_repos(self) -> Dict[str, Any]:
        """
        Migrate global_registry.json to SQLite.

        Returns:
            Migration result with counts.
        """
        source_file = Path(self.source_dir) / "global_registry.json"

        if not source_file.exists():
            logger.info("No global_registry.json found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        try:
            with open(source_file, "r") as f:
                registry_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read global_registry.json: {e}")
            return {"migrated": 0, "errors": 1, "skipped": False}

        backend = GlobalReposSqliteBackend(self.db_path)
        migrated = 0
        already_exists = 0
        errors = 0

        try:
            for alias_name, repo_data in registry_data.items():
                try:
                    backend.register_repo(
                        alias_name=alias_name,
                        repo_name=repo_data.get("repo_name", ""),
                        repo_url=repo_data.get("repo_url"),
                        index_path=repo_data.get("index_path", ""),
                        enable_temporal=repo_data.get("enable_temporal", False),
                        temporal_options=repo_data.get("temporal_options"),
                    )
                    migrated += 1
                    logger.debug(f"Migrated repo: {alias_name}")
                except sqlite3.IntegrityError:
                    already_exists += 1
                    logger.debug(f"Repo already exists, skipping: {alias_name}")
                except Exception as e:
                    logger.error(f"Failed to migrate repo {alias_name}: {e}")
                    errors += 1
        finally:
            backend.close()

        logger.info(
            f"Global repos migration complete: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )

        # Rename JSON file to .migrated after successful migration (Story #702)
        # Only real errors block rename - already_exists is expected for idempotency
        if errors == 0 and (migrated > 0 or already_exists > 0):
            try:
                os.rename(str(source_file), str(source_file) + ".migrated")
                logger.info(f"Renamed {source_file} to {source_file}.migrated")
            except OSError as e:
                logger.warning(f"Failed to rename {source_file} to .migrated: {e}")

        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_users(self) -> Dict[str, Any]:
        """
        Migrate users.json to SQLite with normalized tables.

        Returns:
            Migration result with counts.
        """
        source_file = Path(self.source_dir) / "users.json"

        if not source_file.exists():
            logger.info("No users.json found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        try:
            with open(source_file, "r") as f:
                users_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read users.json: {e}")
            return {"migrated": 0, "errors": 1, "skipped": False}

        backend = UsersSqliteBackend(self.db_path)
        migrated = 0
        already_exists = 0
        errors = 0

        try:
            for username, user_data in users_data.items():
                try:
                    # Create user
                    backend.create_user(
                        username=username,
                        password_hash=user_data.get("password_hash", ""),
                        role=user_data.get("role", "normal_user"),
                        email=user_data.get("email"),
                    )

                    # Migrate API keys
                    api_keys = user_data.get("api_keys", [])
                    for key in api_keys:
                        try:
                            backend.add_api_key(
                                username=username,
                                key_id=key.get("key_id", ""),
                                key_hash=key.get("hash", ""),
                                key_prefix=key.get("key_prefix", ""),
                                name=key.get("name"),
                            )
                        except sqlite3.IntegrityError:
                            pass  # API key already exists, skip

                    # Migrate MCP credentials
                    mcp_creds = user_data.get("mcp_credentials", [])
                    for cred in mcp_creds:
                        try:
                            backend.add_mcp_credential(
                                username=username,
                                credential_id=cred.get("credential_id", ""),
                                client_id=cred.get("client_id", ""),
                                client_secret_hash=cred.get("client_secret_hash", ""),
                                client_id_prefix=cred.get("client_id_prefix", ""),
                                name=cred.get("name"),
                            )
                        except sqlite3.IntegrityError:
                            pass  # MCP credential already exists, skip

                    migrated += 1
                    logger.debug(f"Migrated user: {username}")
                except sqlite3.IntegrityError:
                    # User already exists (e.g., from seed_initial_admin)
                    # UPDATE the password_hash from migrated data - critical for preserving real passwords
                    migrated_password_hash = user_data.get("password_hash", "")
                    if migrated_password_hash:
                        backend.update_password_hash(username, migrated_password_hash)
                        logger.info(f"Updated existing user password_hash from migration: {username}")
                    # Also migrate API keys and MCP credentials for existing users
                    api_keys = user_data.get("api_keys", [])
                    for key in api_keys:
                        try:
                            backend.add_api_key(
                                username=username,
                                key_id=key.get("key_id", ""),
                                key_hash=key.get("hash", ""),
                                key_prefix=key.get("key_prefix", ""),
                                name=key.get("name"),
                            )
                        except sqlite3.IntegrityError:
                            logger.debug(f"API key already exists, skipping: {key.get('key_id', '')}")
                    mcp_creds = user_data.get("mcp_credentials", [])
                    for cred in mcp_creds:
                        try:
                            backend.add_mcp_credential(
                                username=username,
                                credential_id=cred.get("credential_id", ""),
                                client_id=cred.get("client_id", ""),
                                client_secret_hash=cred.get("client_secret_hash", ""),
                                client_id_prefix=cred.get("client_id_prefix", ""),
                                name=cred.get("name"),
                            )
                        except sqlite3.IntegrityError:
                            logger.debug(f"MCP credential already exists, skipping: {cred.get('credential_id', '')}")
                    already_exists += 1
                    logger.debug(f"User already exists, updated from migration: {username}")
                except Exception as e:
                    logger.error(f"Failed to migrate user {username}: {e}")
                    errors += 1
        finally:
            backend.close()

        logger.info(
            f"Users migration complete: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )

        # Rename JSON file to .migrated after successful migration (Story #702)
        # Only real errors block rename - already_exists is expected for idempotency
        if errors == 0 and (migrated > 0 or already_exists > 0):
            try:
                os.rename(str(source_file), str(source_file) + ".migrated")
                logger.info(f"Renamed {source_file} to {source_file}.migrated")
            except OSError as e:
                logger.warning(f"Failed to rename {source_file} to .migrated: {e}")

        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_sync_jobs(self) -> Dict[str, Any]:
        """Migrate jobs.json to SQLite sync_jobs table."""
        source_file = Path(self.source_dir) / "jobs.json"
        if not source_file.exists():
            logger.info("No jobs.json found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        try:
            with open(source_file, "r") as f:
                jobs_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read jobs.json: {e}")
            return {"migrated": 0, "errors": 1, "skipped": False}

        job_records = {k: v for k, v in jobs_data.items() if not k.startswith("_")}
        backend = SyncJobsSqliteBackend(self.db_path)
        migrated, already_exists, errors = 0, 0, 0

        try:
            for job_id, job_data in job_records.items():
                try:
                    backend.create_job(
                        job_id=job_id, username=job_data.get("username", ""),
                        user_alias=job_data.get("user_alias", ""),
                        job_type=job_data.get("job_type", ""),
                        status=job_data.get("status", ""),
                        repository_url=job_data.get("repository_url"),
                    )
                    migrated += 1
                except sqlite3.IntegrityError:
                    already_exists += 1
                    logger.debug(f"Sync job already exists, skipping: {job_id}")
                except Exception as e:
                    logger.error(f"Failed to migrate sync job {job_id}: {e}")
                    errors += 1
        finally:
            backend.close()

        logger.info(
            f"Sync jobs migration: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )
        if errors == 0 and (migrated > 0 or already_exists > 0):
            try:
                os.rename(str(source_file), str(source_file) + ".migrated")
            except OSError as e:
                logger.warning(f"Failed to rename {source_file}: {e}")
        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_ci_tokens(self) -> Dict[str, Any]:
        """Migrate ci_tokens.json to SQLite ci_tokens table."""
        source_file = Path(self.source_dir) / "ci_tokens.json"
        if not source_file.exists():
            logger.info("No ci_tokens.json found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        try:
            with open(source_file, "r") as f:
                tokens_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read ci_tokens.json: {e}")
            return {"migrated": 0, "errors": 1, "skipped": False}

        backend = CITokensSqliteBackend(self.db_path)
        migrated, already_exists, errors = 0, 0, 0

        try:
            for platform, token_data in tokens_data.items():
                try:
                    # Support both "token" (legacy JSON format) and "encrypted_token" keys
                    encrypted_token = token_data.get("token") or token_data.get("encrypted_token", "")
                    backend.save_token(
                        platform=platform,
                        encrypted_token=encrypted_token,
                        base_url=token_data.get("base_url"),
                    )
                    migrated += 1
                except sqlite3.IntegrityError:
                    already_exists += 1
                    logger.debug(f"CI token already exists, skipping: {platform}")
                except Exception as e:
                    logger.error(f"Failed to migrate CI token {platform}: {e}")
                    errors += 1
        finally:
            backend.close()

        logger.info(
            f"CI tokens migration: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )
        if errors == 0 and (migrated > 0 or already_exists > 0):
            try:
                os.rename(str(source_file), str(source_file) + ".migrated")
            except OSError as e:
                logger.warning(f"Failed to rename {source_file}: {e}")
        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_sessions(self) -> Dict[str, Any]:
        """Migrate invalidated_sessions.json to SQLite invalidated_sessions table."""
        source_file = Path(self.source_dir) / "invalidated_sessions.json"
        if not source_file.exists():
            logger.info("No invalidated_sessions.json found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        try:
            with open(source_file, "r") as f:
                sessions_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read invalidated_sessions.json: {e}")
            return {"migrated": 0, "errors": 1, "skipped": False}

        backend = SessionsSqliteBackend(self.db_path)
        migrated, already_exists, errors = 0, 0, 0

        try:
            for username, session_list in sessions_data.items():
                tokens = session_list if isinstance(session_list, list) else list(session_list.keys())
                for token_id in tokens:
                    try:
                        backend.invalidate_session(username=username, token_id=token_id)
                        migrated += 1
                    except sqlite3.IntegrityError:
                        already_exists += 1
                        logger.debug(f"Session already invalidated, skipping: {username}/{token_id}")
                    except Exception as e:
                        logger.error(f"Failed to migrate session {username}/{token_id}: {e}")
                        errors += 1
        finally:
            backend.close()

        logger.info(
            f"Sessions migration: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )
        if errors == 0 and (migrated > 0 or already_exists > 0):
            try:
                os.rename(str(source_file), str(source_file) + ".migrated")
            except OSError as e:
                logger.warning(f"Failed to rename {source_file}: {e}")
        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_ssh_keys(self) -> Dict[str, Any]:
        """Migrate ssh_keys/*.json files to SQLite ssh_keys and ssh_key_hosts tables."""
        ssh_keys_dir = Path(self.source_dir) / "ssh_keys"
        if not ssh_keys_dir.exists():
            logger.info("No ssh_keys directory found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        json_files = list(ssh_keys_dir.glob("*.json"))
        if not json_files:
            logger.info("No SSH key JSON files found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        backend = SSHKeysSqliteBackend(self.db_path)
        migrated, already_exists, errors = 0, 0, 0

        try:
            for json_file in json_files:
                try:
                    with open(json_file, "r") as f:
                        key_data = json.load(f)
                    key_name = key_data.get("name", json_file.stem)
                    backend.create_key(
                        name=key_name, fingerprint=key_data.get("fingerprint", ""),
                        key_type=key_data.get("key_type", ""),
                        private_path=key_data.get("private_path", ""),
                        public_path=key_data.get("public_path", ""),
                        public_key=key_data.get("public_key"),
                        email=key_data.get("email"), description=key_data.get("description"),
                        is_imported=key_data.get("is_imported", False),
                    )
                    for hostname in key_data.get("hosts", []):
                        try:
                            backend.assign_host(key_name=key_name, hostname=hostname)
                        except sqlite3.IntegrityError:
                            pass  # Host assignment already exists
                    migrated += 1
                    os.rename(str(json_file), str(json_file) + ".migrated")
                except sqlite3.IntegrityError:
                    already_exists += 1
                    logger.debug(f"SSH key already exists, skipping: {json_file.stem}")
                    # Still rename file since key exists in DB
                    try:
                        os.rename(str(json_file), str(json_file) + ".migrated")
                    except OSError:
                        pass
                except Exception as e:
                    logger.error(f"Failed to migrate SSH key from {json_file}: {e}")
                    errors += 1
        finally:
            backend.close()

        logger.info(
            f"SSH keys migration: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )
        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_golden_repos_metadata(
        self, golden_repos_dir: str
    ) -> Dict[str, Any]:
        """
        Migrate golden-repos/metadata.json to SQLite golden_repos_metadata table.

        Story #711: Migrate GoldenRepoManager metadata.json to SQLite.

        Args:
            golden_repos_dir: Path to the golden-repos directory containing metadata.json.

        Returns:
            Migration result with counts.
        """
        source_file = Path(golden_repos_dir) / "metadata.json"

        if not source_file.exists():
            logger.info("No golden-repos/metadata.json found, skipping migration")
            return {"migrated": 0, "errors": 0, "skipped": True}

        try:
            with open(source_file, "r") as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read golden-repos/metadata.json: {e}")
            return {"migrated": 0, "errors": 1, "skipped": False}

        backend = GoldenRepoMetadataSqliteBackend(self.db_path)
        migrated, already_exists, errors = 0, 0, 0

        try:
            for alias, repo_data in metadata.items():
                try:
                    backend.add_repo(
                        alias=alias,
                        repo_url=repo_data.get("repo_url", ""),
                        default_branch=repo_data.get("default_branch", "main"),
                        clone_path=repo_data.get("clone_path", ""),
                        created_at=repo_data.get("created_at", ""),
                        enable_temporal=repo_data.get("enable_temporal", False),
                        temporal_options=repo_data.get("temporal_options"),
                    )
                    migrated += 1
                    logger.debug(f"Migrated golden repo: {alias}")
                except sqlite3.IntegrityError:
                    already_exists += 1
                    logger.debug(f"Golden repo already exists, skipping: {alias}")
                except Exception as e:
                    logger.error(f"Failed to migrate golden repo {alias}: {e}")
                    errors += 1
        finally:
            backend.close()

        logger.info(
            f"Golden repos metadata migration: {migrated} migrated, "
            f"{already_exists} already existed, {errors} errors"
        )

        # Rename JSON file to .migrated after successful migration
        if errors == 0 and (migrated > 0 or already_exists > 0):
            try:
                os.rename(str(source_file), str(source_file) + ".migrated")
                logger.info(f"Renamed {source_file} to {source_file}.migrated")
            except OSError as e:
                logger.warning(f"Failed to rename {source_file}: {e}")

        return {
            "migrated": migrated,
            "already_exists": already_exists,
            "errors": errors,
            "skipped": False,
        }

    def migrate_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Run all migrations.

        Returns:
            Dictionary with results for each migration type.
        """
        results = {}

        logger.info("Starting migration of legacy JSON files to SQLite")

        results["global_repos"] = self.migrate_global_repos()
        results["users"] = self.migrate_users()
        results["sync_jobs"] = self.migrate_sync_jobs()
        results["ci_tokens"] = self.migrate_ci_tokens()
        results["sessions"] = self.migrate_sessions()
        results["ssh_keys"] = self.migrate_ssh_keys()

        total_migrated = sum(r.get("migrated", 0) for r in results.values())
        total_errors = sum(r.get("errors", 0) for r in results.values())

        logger.info(
            f"Migration complete: {total_migrated} total records migrated, "
            f"{total_errors} total errors"
        )

        return results
