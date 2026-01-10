"""
Shared constants for CIDX Server services.

This module defines constants for:
- Default group names (admins, powerusers, users)
- Special repository names (cidx-meta)

These constants should be used instead of hardcoded strings throughout
the codebase to ensure consistency and ease of maintenance.
"""

# Default group names
# These are the three groups created at system bootstrap
DEFAULT_GROUP_ADMINS = "admins"
DEFAULT_GROUP_POWERUSERS = "powerusers"
DEFAULT_GROUP_USERS = "users"

# Special repository names
# cidx-meta is always accessible to all groups
CIDX_META_REPO = "cidx-meta"
