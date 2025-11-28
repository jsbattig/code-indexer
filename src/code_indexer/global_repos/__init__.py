"""
Global Repos Module for CIDX.

Provides automatic global activation for golden repositories, allowing
non-power users to query repos immediately without activation commands.
"""

from .global_registry import GlobalRegistry, ReservedNameError
from .alias_manager import AliasManager
from .global_activation import GlobalActivator

__all__ = ["GlobalRegistry", "ReservedNameError", "AliasManager", "GlobalActivator"]
