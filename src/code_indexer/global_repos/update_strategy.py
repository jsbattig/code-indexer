"""
Update Strategy interface for global repository refresh mechanisms.

Defines the abstract interface for different update strategies
(git pull, manual sync, etc.).
"""

from abc import ABC, abstractmethod


class UpdateStrategy(ABC):
    """
    Abstract interface for global repository update mechanisms.

    Implementations provide different ways to update golden repositories
    (e.g., git pull, rsync, manual copy, etc.).
    """

    @abstractmethod
    def has_changes(self) -> bool:
        """
        Check if the repository has changes since last update.

        Returns:
            True if changes detected, False otherwise

        Raises:
            RuntimeError: If change detection fails
        """
        pass

    @abstractmethod
    def update(self) -> None:
        """
        Update the repository to latest version.

        Raises:
            RuntimeError: If update operation fails
        """
        pass

    @abstractmethod
    def get_source_path(self) -> str:
        """
        Get the path to the source repository.

        Returns:
            Absolute path to source repository
        """
        pass
