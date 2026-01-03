"""
Test fixtures for CIDX integration testing.

Provides reusable test infrastructure including:
- MockGitRepository: Real git repositories for testing (NO Python mocks)
"""

from .mock_git_repository import MockGitRepository

__all__ = ["MockGitRepository"]
