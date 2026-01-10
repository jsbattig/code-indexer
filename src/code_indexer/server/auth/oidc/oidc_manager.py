"""OIDC manager for orchestrating OIDC authentication flow."""

from pathlib import Path
from code_indexer.server.middleware.correlation import get_correlation_id


class OIDCManager:
    def __init__(self, config, user_manager, jwt_manager):
        self.config = config
        self.user_manager = user_manager
        self.jwt_manager = jwt_manager
        self.provider = None
        # Use existing oauth.db instead of separate database
        self.db_path = str(Path.home() / ".cidx-server" / "oauth.db")

    async def initialize(self):
        """Initialize database schema (no network calls)."""
        if self.config.enabled:
            # Initialize database schema for OIDC identity links
            await self._init_db()

    async def ensure_provider_initialized(self):
        """Lazily initialize OIDC provider (discovers metadata via network call).

        This is called on-demand during SSO login to avoid blocking server startup.
        If the OIDC provider is unreachable, this will fail gracefully and log an error.
        """
        if self.provider is None and self.config.enabled:
            import logging
            from .oidc_provider import OIDCProvider

            logger = logging.getLogger(__name__)
            logger.info(
                "Initializing SSO provider",
                extra={"correlation_id": get_correlation_id()},
            )

            try:
                # Create provider and discover metadata atomically
                # Only set self.provider if both succeed
                provider = OIDCProvider(self.config)
                provider._metadata = await provider.discover_metadata()

                # Success - now we can set self.provider
                self.provider = provider
                logger.info(
                    "SSO provider initialized successfully",
                    extra={"correlation_id": get_correlation_id()},
                )
            except Exception as e:
                logger.error(
                    f"Failed to initialize SSO provider: {e}",
                    exc_info=True,
                    extra={"correlation_id": get_correlation_id()},
                )
                # Don't set self.provider - leave it None so we can retry
                raise

    def is_enabled(self):
        """Check if OIDC is enabled in configuration."""
        return self.config.enabled

    def _ensure_group_membership(self, username: str) -> None:
        """Ensure user has group membership via SSO provisioning hook.

        Story #708: SSO Auto-Provisioning with Default Group Assignment
        - AC1: New SSO users assigned to "users" group
        - AC3: Existing users' membership is NOT changed
        - AC6: Errors are logged but do not block authentication

        Args:
            username: The user's username to provision
        """
        import logging

        logger = logging.getLogger(__name__)

        # Check if group_manager is available (injected via app.py)
        if not hasattr(self, "group_manager") or self.group_manager is None:
            logger.warning(
                f"Group manager not available, skipping SSO provisioning for {username}",
                extra={"correlation_id": get_correlation_id()},
            )
            return

        try:
            from code_indexer.server.services.sso_provisioning_hook import (
                ensure_user_group_membership,
            )

            result = ensure_user_group_membership(username, self.group_manager)
            if result:
                logger.debug(
                    f"SSO provisioning completed for user {username}",
                    extra={"correlation_id": get_correlation_id()},
                )
            else:
                logger.warning(
                    f"SSO provisioning returned False for user {username}",
                    extra={"correlation_id": get_correlation_id()},
                )
        except Exception as e:
            # AC6: Errors are logged but do not block authentication
            logger.error(
                f"SSO provisioning failed for user {username}: {e}. "
                f"User will have fallback cidx-meta-only access.",
                extra={"correlation_id": get_correlation_id()},
            )

    def create_jwt_session(self, user):
        return self.jwt_manager.create_token(
            {
                "username": user.username,
                "role": user.role.value,
                "created_at": user.created_at.isoformat(),
            }
        )

    async def _init_db(self):
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS oidc_identity_links (
                    username TEXT NOT NULL PRIMARY KEY,
                    subject TEXT NOT NULL UNIQUE,
                    email TEXT,
                    linked_at TEXT NOT NULL,
                    last_login TEXT
                )
            """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_oidc_subject ON oidc_identity_links (subject)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_oidc_email ON oidc_identity_links (email)"
            )
            await db.commit()

    async def link_oidc_identity(self, username, subject, email):
        import aiosqlite
        from datetime import datetime, timezone

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO oidc_identity_links (username, subject, email, linked_at, last_login)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    username,
                    subject,
                    email,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def match_or_create_user(self, user_info):
        import aiosqlite
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"match_or_create_user called with subject={user_info.subject}, email={user_info.email}, email_verified={user_info.email_verified}",
            extra={"correlation_id": get_correlation_id()},
        )

        # Check if OIDC subject already exists in database (fast path)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT username FROM oidc_identity_links WHERE subject = ?",
                (user_info.subject,),
            )
            result = await cursor.fetchone()

            if result:
                # Subject exists, check if user still exists
                username = result[0]
                logger.info(
                    f"Found existing OIDC link: subject={user_info.subject} -> username={username}",
                    extra={"correlation_id": get_correlation_id()},
                )
                existing_user = self.user_manager.get_user(username)
                if existing_user:
                    logger.info(
                        f"Returning existing user: {username}",
                        extra={"correlation_id": get_correlation_id()},
                    )
                    # Story #708: Ensure group membership on every SSO login
                    self._ensure_group_membership(existing_user.username)
                    return existing_user
                else:
                    # Stale OIDC link (defensive check - should be cleaned up on user deletion)
                    logger.warning(
                        f"Stale OIDC link found for subject={user_info.subject}, deleting",
                        extra={"correlation_id": get_correlation_id()},
                    )
                    await db.execute(
                        "DELETE FROM oidc_identity_links WHERE subject = ?",
                        (user_info.subject,),
                    )
                    await db.commit()
                    # Fall through to auto-link or JIT provisioning

        # Check if email matches existing user (auto-link)
        # Respect require_email_verification config setting
        if user_info.email:
            if not self.config.require_email_verification or user_info.email_verified:
                existing_user = self.user_manager.get_user_by_email(user_info.email)
                if existing_user:
                    # Auto-link OIDC identity to existing user
                    await self.link_oidc_identity(
                        username=existing_user.username,
                        subject=user_info.subject,
                        email=user_info.email,
                    )
                    # Story #708: Ensure group membership on every SSO login
                    self._ensure_group_membership(existing_user.username)
                    return existing_user

        # Create new user via JIT provisioning if enabled
        if self.config.enable_jit_provisioning:
            from code_indexer.server.auth.user_manager import UserRole
            from datetime import datetime, timezone

            # Check email verification requirement
            if self.config.require_email_verification and not user_info.email_verified:
                # Email verification required but not verified - reject login
                return None

            # Extract username from configured username_claim
            # If username_claim is configured but not present in userinfo, fail
            if not user_info.username:
                logger.error(
                    f"Username claim '{self.config.username_claim}' not found in OIDC userinfo. Available claims: {list(user_info.__dict__.keys())}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return None

            base_username = user_info.username
            logger.info(
                f"Using username from OIDC username_claim '{self.config.username_claim}': {base_username}",
                extra={"correlation_id": get_correlation_id()},
            )

            # Check if username already exists (collision detection)
            if self.user_manager.get_user(base_username):
                logger.error(
                    f"JIT provisioning failed: Username '{base_username}' already exists. "
                    f"OIDC subject={user_info.subject}, email={user_info.email}. "
                    f"Admin must manually link accounts or resolve username conflict.",
                    extra={"correlation_id": get_correlation_id()},
                )
                return None

            # Create OIDC identity data
            oidc_identity = {
                "subject": user_info.subject,
                "email": user_info.email,
                "linked_at": datetime.now(timezone.utc).isoformat(),
                "last_login": datetime.now(timezone.utc).isoformat(),
            }

            # Create new user
            new_user = self.user_manager.create_oidc_user(
                username=base_username,
                role=UserRole[self.config.default_role.upper()],
                email=user_info.email,
                oidc_identity=oidc_identity,
            )

            # Link OIDC identity in database
            await self.link_oidc_identity(
                username=new_user.username,
                subject=user_info.subject,
                email=user_info.email,
            )

            # Story #708: Ensure group membership for new JIT-provisioned user
            self._ensure_group_membership(new_user.username)

            return new_user
