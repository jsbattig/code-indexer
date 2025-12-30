"""OIDC manager for orchestrating OIDC authentication flow."""

from pathlib import Path


class OIDCManager:
    def __init__(self, config, user_manager, jwt_manager):
        self.config = config
        self.user_manager = user_manager
        self.jwt_manager = jwt_manager
        self.provider = None
        # Use existing oauth.db instead of separate database
        self.db_path = str(Path.home() / ".cidx-server" / "oauth.db")

    async def initialize(self):
        if self.config.enabled:
            from .oidc_provider import OIDCProvider

            self.provider = OIDCProvider(self.config)
            self.provider._metadata = await self.provider.discover_metadata()

            # Initialize database schema for OIDC identity links
            await self._init_db()

    def is_enabled(self):
        return self.config.enabled and self.provider is not None

    def create_jwt_session(self, user):
        return self.jwt_manager.create_token({
            "username": user.username,
            "role": user.role.value,
            "created_at": user.created_at.isoformat(),
        })

    async def _init_db(self):
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS oidc_identity_links (
                    username TEXT NOT NULL PRIMARY KEY,
                    subject TEXT NOT NULL UNIQUE,
                    email TEXT,
                    linked_at TEXT NOT NULL,
                    last_login TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_oidc_subject ON oidc_identity_links (subject)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_oidc_email ON oidc_identity_links (email)")
            await db.commit()

    async def link_oidc_identity(self, username, subject, email):
        import aiosqlite
        from datetime import datetime, timezone

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO oidc_identity_links (username, subject, email, linked_at, last_login)
                VALUES (?, ?, ?, ?, ?)
            """, (username, subject, email, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
            await db.commit()

    async def match_or_create_user(self, user_info):
        import aiosqlite

        # Check if OIDC subject already exists in database (fast path)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT username FROM oidc_identity_links WHERE subject = ?",
                (user_info.subject,)
            )
            result = await cursor.fetchone()

            if result:
                # Subject exists, check if user still exists
                username = result[0]
                existing_user = self.user_manager.get_user(username)
                if existing_user:
                    return existing_user
                else:
                    # Stale OIDC link (defensive check - should be cleaned up on user deletion)
                    await db.execute(
                        "DELETE FROM oidc_identity_links WHERE subject = ?",
                        (user_info.subject,)
                    )
                    await db.commit()
                    # Fall through to auto-link or JIT provisioning

        # Check if verified email matches existing user (auto-link)
        if user_info.email and user_info.email_verified:
            existing_user = self.user_manager.get_user_by_email(user_info.email)
            if existing_user:
                # Auto-link OIDC identity to existing user
                await self.link_oidc_identity(
                    username=existing_user.username,
                    subject=user_info.subject,
                    email=user_info.email
                )
                return existing_user

        # Create new user via JIT provisioning if enabled
        if self.config.enable_jit_provisioning:
            from code_indexer.server.auth.user_manager import UserRole
            from datetime import datetime, timezone

            # Generate username from email or subject
            if user_info.email:
                base_username = user_info.email.split('@')[0]
            else:
                base_username = user_info.subject.replace('-', '_')[:20]

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
                oidc_identity=oidc_identity
            )

            # Link OIDC identity in database
            await self.link_oidc_identity(
                username=new_user.username,
                subject=user_info.subject,
                email=user_info.email
            )

            return new_user
