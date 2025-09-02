#!/usr/bin/env python3
"""
Main application entry point for the CIDX test application.

This module provides the core application functionality including
initialization, configuration loading, and main execution flow.
"""

import sys
from typing import Optional, Dict, Any

from config.settings import load_configuration, ConfigurationError
from config.logging import setup_logging
from api import create_app
from database import DatabaseManager
from auth import AuthenticationManager


class Application:
    """Main application class that orchestrates all components."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the application with configuration.

        Args:
            config_path: Optional path to configuration file
        """
        self.config = None
        self.db_manager = None
        self.auth_manager = None
        self.app = None
        self.logger = None

        try:
            self.config = load_configuration(config_path)
            self.logger = setup_logging(self.config)
            self.logger.info("Application initialized successfully")
        except ConfigurationError as e:
            print(f"Configuration error: {e}")
            sys.exit(1)

    def initialize_components(self) -> None:
        """Initialize all application components."""
        try:
            # Initialize database manager
            self.db_manager = DatabaseManager(
                connection_string=self.config.database_url,
                pool_size=self.config.db_pool_size,
            )

            # Initialize authentication manager
            self.auth_manager = AuthenticationManager(
                secret_key=self.config.secret_key,
                token_expiry=self.config.token_expiry_minutes,
            )

            # Create Flask/FastAPI application
            self.app = create_app(
                config=self.config,
                db_manager=self.db_manager,
                auth_manager=self.auth_manager,
            )

            self.logger.info("All components initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise

    def run_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Run the application server.

        Args:
            host: Host address to bind to
            port: Port number to listen on
        """
        if not self.app:
            self.initialize_components()

        self.logger.info(f"Starting server on {host}:{port}")

        try:
            # In a real application, this would use uvicorn or gunicorn
            self.app.run(host=host, port=port, debug=self.config.debug_mode)
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            raise

    def run_migration(self) -> None:
        """Run database migrations."""
        if not self.db_manager:
            self.initialize_components()

        self.logger.info("Running database migrations")
        self.db_manager.run_migrations()
        self.logger.info("Database migrations completed")

    def health_check(self) -> Dict[str, Any]:
        """
        Perform application health check.

        Returns:
            Dict containing health status information
        """
        status = {
            "status": "healthy",
            "timestamp": self._get_current_timestamp(),
            "version": self.config.app_version if self.config else "unknown",
            "components": {},
        }

        # Check database connectivity
        if self.db_manager:
            try:
                self.db_manager.health_check()
                status["components"]["database"] = "healthy"
            except Exception as e:
                status["components"]["database"] = f"unhealthy: {e}"
                status["status"] = "degraded"

        # Check authentication service
        if self.auth_manager:
            try:
                self.auth_manager.health_check()
                status["components"]["authentication"] = "healthy"
            except Exception as e:
                status["components"]["authentication"] = f"unhealthy: {e}"
                status["status"] = "degraded"

        return status

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


def main() -> int:
    """
    Main application entry point.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    import argparse

    parser = argparse.ArgumentParser(description="CIDX Test Application")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument(
        "--migrate", action="store_true", help="Run database migrations"
    )
    parser.add_argument("--health", action="store_true", help="Perform health check")

    args = parser.parse_args()

    try:
        app = Application(args.config)

        if args.migrate:
            app.run_migration()
            return 0

        if args.health:
            health_status = app.health_check()
            print(f"Health Status: {health_status}")
            return 0 if health_status["status"] == "healthy" else 1

        # Default: run server
        app.run_server(host=args.host, port=args.port)
        return 0

    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        return 0
    except Exception as e:
        print(f"Application error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
