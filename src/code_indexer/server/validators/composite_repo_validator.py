"""
Composite Repository Validator for CIDX Server.

This module validates operations on composite repositories to ensure
unsupported operations are properly blocked with clear error messages.

Based on CLI's command_validator.py logic, this validator prevents
operations that don't make sense in proxy/composite mode.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import json
import logging
from pathlib import Path
from typing import Dict

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class CompositeRepoValidator:
    """
    Validates operations on composite repositories.

    This validator checks if a repository is in proxy mode (composite)
    and blocks operations that are not supported in that mode.

    Unsupported operations on composite repositories:
    - branch_switch: Branch operations don't apply to composite repos
    - branch_list: Branch operations don't apply to composite repos
    - sync: Sync must be done on individual golden repos
    - index: Indexing must be done on individual golden repos
    - reconcile: Reconciliation must be done on individual repos
    - init: Composite repos cannot be initialized directly
    """

    UNSUPPORTED_OPERATIONS: Dict[str, str] = {
        "branch_switch": "Branch operations are not supported for composite repositories",
        "branch_list": "Branch operations are not supported for composite repositories",
        "sync": "Sync is not supported for composite repositories",
        "index": "Indexing must be done on individual golden repositories",
        "reconcile": "Reconciliation is not supported for composite repositories",
        "init": "Composite repositories cannot be initialized",
    }

    @staticmethod
    def check_operation(repo_path: Path, operation: str) -> None:
        """
        Check if operation is supported on the repository.

        This method validates whether a given operation can be performed on
        a repository. If the repository is in proxy mode (composite) and the
        operation is not supported, it raises an HTTP 400 error with a clear
        explanation of the limitation.

        Early return conditions:
        - Repository has no config file (not a composite repo)
        - Config file is malformed (gracefully allow operation)
        - Repository is not in proxy mode (single repo)
        - Operation is not in the unsupported list

        Args:
            repo_path: Path to the repository to validate
            operation: Operation name to check (e.g., 'branch_switch', 'sync')

        Raises:
            HTTPException: 400 status if operation is not supported on composite repo

        Example:
            >>> CompositeRepoValidator.check_operation(
            ...     Path("/path/to/composite/repo"),
            ...     'branch_switch'
            ... )
            HTTPException: Branch operations are not supported for composite repositories
        """
        config_file = repo_path / ".code-indexer" / "config.json"

        # If no config file exists, it's not a composite repo
        if not config_file.exists():
            return

        try:
            config = json.loads(config_file.read_text())

            # Check if repository is in proxy mode (composite)
            if config.get("proxy_mode", False):
                # Check if operation is unsupported
                if operation in CompositeRepoValidator.UNSUPPORTED_OPERATIONS:
                    error_message = CompositeRepoValidator.UNSUPPORTED_OPERATIONS[
                        operation
                    ]
                    logger.warning(
                        f"Blocked unsupported operation '{operation}' on composite repository: {repo_path}"
                    , extra={"correlation_id": get_correlation_id()})
                    raise HTTPException(status_code=400, detail=error_message)

        except json.JSONDecodeError as e:
            # If config file is malformed, log but don't block operation
            # This is a graceful degradation - we don't want to break operations
            # due to corrupted config files
            logger.error(f"Failed to parse config file {config_file}: {e}", extra={"correlation_id": get_correlation_id()})
            return
