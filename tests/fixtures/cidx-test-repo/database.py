"""
Database models and connection handling for the CIDX test application.

This module provides ORM models, database connectivity, and data access
patterns for user management, search queries, and repository tracking.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from auth import UserRole


logger = logging.getLogger(__name__)
Base = declarative_base()


@dataclass
class ConnectionConfig:
    """Database connection configuration."""

    url: str
    pool_size: int = 5
    pool_timeout: int = 30
    echo_sql: bool = False


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="normal_user")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    search_queries = relationship(
        "SearchQuery", back_populates="user", cascade="all, delete-orphan"
    )
    repositories = relationship(
        "UserRepository", back_populates="user", cascade="all, delete-orphan"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary representation."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

    @property
    def role_enum(self) -> UserRole:
        """Get user role as enum."""
        return UserRole(self.role)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class Repository(Base):
    """Repository model for tracking indexed code repositories."""

    __tablename__ = "repositories"

    id = Column(String(50), primary_key=True)  # UUID or hash-based ID
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    path = Column(String(1000), nullable=False)
    git_url = Column(String(500), nullable=True)
    branch = Column(String(100), default="master")
    is_active = Column(Boolean, default=True, nullable=False)
    indexing_status = Column(
        String(20), default="pending"
    )  # pending, indexing, indexed, error
    last_indexed = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Metadata
    total_files = Column(Integer, default=0)
    indexed_files = Column(Integer, default=0)
    total_lines = Column(Integer, default=0)
    primary_language = Column(String(50), nullable=True)

    # Relationships
    user_repositories = relationship(
        "UserRepository", back_populates="repository", cascade="all, delete-orphan"
    )
    search_queries = relationship("SearchQuery", back_populates="repository")

    def to_dict(self) -> Dict[str, Any]:
        """Convert repository to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "git_url": self.git_url,
            "branch": self.branch,
            "is_active": self.is_active,
            "indexing_status": self.indexing_status,
            "last_indexed": (
                self.last_indexed.isoformat() if self.last_indexed else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "total_files": self.total_files,
            "indexed_files": self.indexed_files,
            "total_lines": self.total_lines,
            "primary_language": self.primary_language,
        }

    @property
    def indexing_progress(self) -> float:
        """Get indexing progress as percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.indexed_files / self.total_files) * 100

    def __repr__(self) -> str:
        return f"<Repository(id='{self.id}', name='{self.name}', status='{self.indexing_status}')>"


class UserRepository(Base):
    """Association table for user-repository access control."""

    __tablename__ = "user_repositories"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    repository_id = Column(String(50), ForeignKey("repositories.id"), primary_key=True)
    access_level = Column(String(20), default="read")  # read, write, admin
    granted_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="repositories")
    repository = relationship("Repository", back_populates="user_repositories")

    def to_dict(self) -> Dict[str, Any]:
        """Convert user repository access to dictionary representation."""
        return {
            "user_id": self.user_id,
            "repository_id": self.repository_id,
            "access_level": self.access_level,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "granted_by": self.granted_by,
        }


class SearchQuery(Base):
    """Search query logging for analytics and history."""

    __tablename__ = "search_queries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    repository_id = Column(
        String(50), ForeignKey("repositories.id"), nullable=True, index=True
    )
    query = Column(Text, nullable=False)
    results_count = Column(Integer, default=0)
    execution_time_ms = Column(Integer, nullable=True)
    timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # Relationships
    user = relationship("User", back_populates="search_queries")
    repository = relationship("Repository", back_populates="search_queries")

    def to_dict(self) -> Dict[str, Any]:
        """Convert search query to dictionary representation."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "repository_id": self.repository_id,
            "query": self.query,
            "results_count": self.results_count,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self) -> str:
        return f"<SearchQuery(id={self.id}, user_id={self.user_id}, query='{self.query[:50]}...')>"


class DatabaseManager:
    """Database connection and operations manager."""

    def __init__(self, connection_config: Union[ConnectionConfig, str]):
        """
        Initialize database manager.

        Args:
            connection_config: Database connection configuration or URL string
        """
        if isinstance(connection_config, str):
            self.config = ConnectionConfig(url=connection_config)
        else:
            self.config = connection_config

        self.engine = None
        self.session_factory = None
        self.logger = logging.getLogger(f"{__name__}.DatabaseManager")

        self._initialize_engine()

    def _initialize_engine(self) -> None:
        """Initialize SQLAlchemy engine and session factory."""
        try:
            self.engine = create_engine(
                self.config.url,
                pool_size=self.config.pool_size,
                pool_timeout=self.config.pool_timeout,
                echo=self.config.echo_sql,
            )

            self.session_factory = sessionmaker(bind=self.engine)
            self.logger.info(f"Database engine initialized: {self.config.url}")

        except Exception as e:
            self.logger.error(f"Failed to initialize database engine: {e}")
            raise

    def create_tables(self) -> None:
        """Create all database tables."""
        try:
            Base.metadata.create_all(self.engine)
            self.logger.info("Database tables created successfully")
        except Exception as e:
            self.logger.error(f"Failed to create database tables: {e}")
            raise

    def drop_tables(self) -> None:
        """Drop all database tables (use with caution)."""
        try:
            Base.metadata.drop_all(self.engine)
            self.logger.warning("All database tables dropped")
        except Exception as e:
            self.logger.error(f"Failed to drop database tables: {e}")
            raise

    @contextmanager
    def session_scope(self):
        """Provide database session with automatic commit/rollback."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def health_check(self) -> bool:
        """
        Perform database health check.

        Returns:
            True if database is healthy

        Raises:
            Exception: If database is not accessible
        """
        try:
            with self.session_scope() as session:
                # Simple query to test connectivity
                session.execute("SELECT 1")
                return True
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            raise

    # User management methods
    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str = None,
        role: UserRole = UserRole.NORMAL_USER,
    ) -> User:
        """
        Create new user.

        Args:
            username: Unique username
            password_hash: Hashed password
            email: Optional email address
            role: User role

        Returns:
            Created User object
        """
        with self.session_scope() as session:
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                role=role.value,
            )

            session.add(user)
            session.flush()  # Get the user ID

            self.logger.info(f"User created: {username} (ID: {user.id})")
            return user

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        with self.session_scope() as session:
            return session.query(User).filter(User.username == username).first()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        with self.session_scope() as session:
            return session.query(User).filter(User.id == user_id).first()

    def get_all_users(self) -> List[User]:
        """Get all users."""
        with self.session_scope() as session:
            return session.query(User).all()

    def update_user_last_login(self, user_id: int) -> bool:
        """Update user's last login timestamp."""
        with self.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.last_login = datetime.now(timezone.utc)
                return True
            return False

    # Repository management methods
    def create_repository(
        self,
        repo_id: str,
        name: str,
        path: str,
        description: str = None,
        git_url: str = None,
    ) -> Repository:
        """Create new repository."""
        with self.session_scope() as session:
            repository = Repository(
                id=repo_id,
                name=name,
                description=description,
                path=path,
                git_url=git_url,
            )

            session.add(repository)
            session.flush()

            self.logger.info(f"Repository created: {name} (ID: {repo_id})")
            return repository

    def get_repository(self, repo_id: str) -> Optional[Repository]:
        """Get repository by ID."""
        with self.session_scope() as session:
            return session.query(Repository).filter(Repository.id == repo_id).first()

    def get_user_repositories(self, user_id: int) -> List[Repository]:
        """Get repositories accessible to user."""
        with self.session_scope() as session:
            return (
                session.query(Repository)
                .join(UserRepository)
                .filter(UserRepository.user_id == user_id)
                .all()
            )

    def grant_repository_access(
        self,
        user_id: int,
        repo_id: str,
        access_level: str = "read",
        granted_by: int = None,
    ) -> bool:
        """Grant user access to repository."""
        with self.session_scope() as session:
            # Check if access already exists
            existing = (
                session.query(UserRepository)
                .filter(
                    UserRepository.user_id == user_id,
                    UserRepository.repository_id == repo_id,
                )
                .first()
            )

            if existing:
                existing.access_level = access_level
                existing.granted_by = granted_by
            else:
                user_repo = UserRepository(
                    user_id=user_id,
                    repository_id=repo_id,
                    access_level=access_level,
                    granted_by=granted_by,
                )
                session.add(user_repo)

            return True

    def user_has_repo_access(self, user_id: int, repo_id: str) -> bool:
        """Check if user has access to repository."""
        with self.session_scope() as session:
            return (
                session.query(UserRepository)
                .filter(
                    UserRepository.user_id == user_id,
                    UserRepository.repository_id == repo_id,
                )
                .first()
                is not None
            )

    def get_repository_status(self, repo_id: str) -> Dict[str, Any]:
        """Get repository indexing status."""
        repository = self.get_repository(repo_id)
        if not repository:
            return {"error": "Repository not found"}

        return {
            "id": repository.id,
            "name": repository.name,
            "indexing_status": repository.indexing_status,
            "progress": repository.indexing_progress,
            "last_indexed": (
                repository.last_indexed.isoformat() if repository.last_indexed else None
            ),
            "total_files": repository.total_files,
            "indexed_files": repository.indexed_files,
            "primary_language": repository.primary_language,
        }

    # Search query logging methods
    def log_search_query(
        self,
        user_id: int,
        query: str,
        repository_id: str = None,
        results_count: int = 0,
        execution_time_ms: int = None,
    ) -> SearchQuery:
        """Log search query for analytics."""
        with self.session_scope() as session:
            search_query = SearchQuery(
                user_id=user_id,
                repository_id=repository_id,
                query=query,
                results_count=results_count,
                execution_time_ms=execution_time_ms,
            )

            session.add(search_query)
            session.flush()

            return search_query

    def get_user_search_history(
        self, user_id: int, limit: int = 50
    ) -> List[SearchQuery]:
        """Get user's search history."""
        with self.session_scope() as session:
            return (
                session.query(SearchQuery)
                .filter(SearchQuery.user_id == user_id)
                .order_by(SearchQuery.timestamp.desc())
                .limit(limit)
                .all()
            )

    def get_search_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get search analytics for the specified period."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        with self.session_scope() as session:
            queries = (
                session.query(SearchQuery)
                .filter(SearchQuery.timestamp >= cutoff_date)
                .all()
            )

            return {
                "total_queries": len(queries),
                "unique_users": len(set(q.user_id for q in queries)),
                "average_execution_time": (
                    sum(q.execution_time_ms for q in queries if q.execution_time_ms)
                    / len([q for q in queries if q.execution_time_ms])
                    if queries
                    else 0
                ),
                "most_common_queries": self._get_most_common_queries(queries),
                "period_days": days,
            }

    def _get_most_common_queries(
        self, queries: List[SearchQuery], top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most common queries from the list."""
        from collections import Counter

        query_counts = Counter(q.query for q in queries)
        most_common = query_counts.most_common(top_n)

        return [{"query": query, "count": count} for query, count in most_common]

    def run_migrations(self) -> None:
        """Run database migrations (placeholder for migration system)."""
        self.logger.info("Running database migrations...")

        # In a real application, this would use Alembic or similar
        # For now, just create tables if they don't exist
        self.create_tables()

        # Add any data migrations here
        self._ensure_admin_user_exists()

        self.logger.info("Database migrations completed")

    def _ensure_admin_user_exists(self) -> None:
        """Ensure at least one admin user exists."""
        with self.session_scope() as session:
            admin_user = session.query(User).filter(User.role == "admin").first()

            if not admin_user:
                # Create default admin user
                from auth import PasswordManager

                pwd_manager = PasswordManager()

                default_admin = User(
                    username="admin",
                    password_hash=pwd_manager.hash_password("admin"),
                    role="admin",
                    email="admin@example.com",
                )

                session.add(default_admin)
                session.flush()

                self.logger.warning(
                    "Default admin user created (admin/admin) - change password immediately!"
                )


# Connection helper functions
def create_sqlite_database(db_path: Union[str, Path]) -> DatabaseManager:
    """
    Create SQLite database manager.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Configured DatabaseManager instance
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection_url = f"sqlite:///{db_path}"
    config = ConnectionConfig(url=connection_url, echo_sql=False)

    db_manager = DatabaseManager(config)
    db_manager.create_tables()

    return db_manager


def create_memory_database() -> DatabaseManager:
    """
    Create in-memory SQLite database for testing.

    Returns:
        DatabaseManager with in-memory database
    """
    config = ConnectionConfig(url="sqlite:///:memory:", echo_sql=False)
    db_manager = DatabaseManager(config)
    db_manager.create_tables()

    return db_manager
