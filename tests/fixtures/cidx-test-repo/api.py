"""
REST API implementation for the CIDX test application.

This module provides HTTP endpoints for various application operations
including authentication, data retrieval, and administrative functions.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any
from functools import wraps

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.exceptions import BadRequest, Unauthorized, Forbidden, NotFound

from auth import AuthenticationManager, UserRole
from database import DatabaseManager, SearchQuery
from utils import validate_json_schema, rate_limit, sanitize_input


logger = logging.getLogger(__name__)


def require_authentication(f):
    """Decorator to require valid authentication for API endpoints."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise Unauthorized("Authentication required")

        try:
            # Extract token from "Bearer <token>" format
            scheme, token = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise Unauthorized("Invalid authentication scheme")

            # Validate token and get user info
            user_info = g.auth_manager.validate_token(token)
            g.current_user = user_info

        except ValueError:
            raise Unauthorized("Invalid authorization header format")
        except Exception as e:
            logger.warning(f"Authentication failed: {e}")
            raise Unauthorized("Invalid or expired token")

        return f(*args, **kwargs)

    return decorated_function


def require_role(required_role: UserRole):
    """Decorator to require specific user role for API endpoints."""

    def decorator(f):
        @wraps(f)
        @require_authentication
        def decorated_function(*args, **kwargs):
            current_user_role = UserRole(g.current_user.get("role"))

            # Admin users can access everything
            if current_user_role == UserRole.ADMIN:
                return f(*args, **kwargs)

            # Check if user has required role or higher
            if current_user_role.value < required_role.value:
                raise Forbidden("Insufficient privileges")

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def create_app(
    config, db_manager: DatabaseManager, auth_manager: AuthenticationManager
) -> Flask:
    """
    Create and configure Flask application.

    Args:
        config: Application configuration object
        db_manager: Database manager instance
        auth_manager: Authentication manager instance

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    app.config.update(config.flask_config)

    # Enable CORS for frontend integration
    CORS(app, origins=config.allowed_origins)

    # Store managers in app context
    app.db_manager = db_manager
    app.auth_manager = auth_manager

    @app.before_request
    def before_request():
        """Set up request context."""
        g.db_manager = app.db_manager
        g.auth_manager = app.auth_manager
        g.request_id = generate_request_id()

        logger.info(f"Request {g.request_id}: {request.method} {request.path}")

    @app.after_request
    def after_request(response):
        """Clean up after request."""
        logger.info(f"Response {g.request_id}: {response.status_code}")
        return response

    @app.errorhandler(400)
    def handle_bad_request(error):
        return jsonify({"error": "Bad request", "message": str(error)}), 400

    @app.errorhandler(401)
    def handle_unauthorized(error):
        return jsonify({"error": "Unauthorized", "message": str(error)}), 401

    @app.errorhandler(403)
    def handle_forbidden(error):
        return jsonify({"error": "Forbidden", "message": str(error)}), 403

    @app.errorhandler(404)
    def handle_not_found(error):
        return jsonify({"error": "Not found", "message": str(error)}), 404

    @app.errorhandler(500)
    def handle_internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({"error": "Internal server error"}), 500

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint for monitoring."""
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": config.app_version,
            }

            # Check database connectivity
            g.db_manager.health_check()

            return jsonify(health_status)

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return (
                jsonify(
                    {
                        "status": "unhealthy",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                503,
            )

    # Authentication endpoints
    @app.route("/auth/login", methods=["POST"])
    @rate_limit(max_requests=5, window_minutes=1)
    def login():
        """User authentication endpoint."""
        data = request.get_json()

        if not data or "username" not in data or "password" not in data:
            raise BadRequest("Username and password required")

        username = sanitize_input(data["username"])
        password = data["password"]

        try:
            # Authenticate user
            user_info = g.auth_manager.authenticate_user(username, password)

            # Generate JWT token
            token = g.auth_manager.generate_token(user_info)

            logger.info(f"User {username} logged in successfully")

            return jsonify(
                {
                    "access_token": token,
                    "token_type": "bearer",
                    "user": {
                        "username": user_info["username"],
                        "role": user_info["role"],
                    },
                }
            )

        except Exception as e:
            logger.warning(f"Login failed for {username}: {e}")
            raise Unauthorized("Invalid username or password")

    @app.route("/auth/refresh", methods=["POST"])
    @require_authentication
    def refresh_token():
        """Token refresh endpoint."""
        try:
            new_token = g.auth_manager.refresh_token(g.current_user)

            return jsonify({"access_token": new_token, "token_type": "bearer"})

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise Unauthorized("Token refresh failed")

    # User management endpoints
    @app.route("/api/users", methods=["GET"])
    @require_role(UserRole.ADMIN)
    def list_users():
        """List all users (admin only)."""
        try:
            users = g.db_manager.get_all_users()

            return jsonify(
                {"users": [user.to_dict() for user in users], "total": len(users)}
            )

        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            raise

    @app.route("/api/users", methods=["POST"])
    @require_role(UserRole.ADMIN)
    def create_user():
        """Create new user (admin only)."""
        data = request.get_json()

        schema = {
            "username": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "role": {"type": "string", "required": True},
        }

        validate_json_schema(data, schema)

        try:
            user = g.db_manager.create_user(
                username=sanitize_input(data["username"]),
                password=data["password"],
                role=UserRole(data["role"]),
            )

            logger.info(f"User {user.username} created by {g.current_user['username']}")

            return (
                jsonify(
                    {"message": "User created successfully", "user": user.to_dict()}
                ),
                201,
            )

        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise BadRequest(f"User creation failed: {e}")

    # Search endpoints
    @app.route("/api/search", methods=["POST"])
    @require_authentication
    def semantic_search():
        """Semantic code search endpoint."""
        data = request.get_json()

        if not data or "query" not in data:
            raise BadRequest("Search query required")

        query_text = sanitize_input(data["query"])
        limit = data.get("limit", 10)

        if limit > 100:
            limit = 100  # Prevent excessive results

        try:
            # Log search query
            search_query = SearchQuery(
                user_id=g.current_user["user_id"],
                query=query_text,
                timestamp=datetime.now(timezone.utc),
            )
            g.db_manager.log_search_query(search_query)

            # Perform semantic search
            results = perform_semantic_search(query_text, limit)

            logger.info(
                f"Search by {g.current_user['username']}: {query_text} ({len(results)} results)"
            )

            return jsonify(
                {"query": query_text, "results": results, "total": len(results)}
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    @app.route("/api/search/history", methods=["GET"])
    @require_authentication
    def search_history():
        """Get user's search history."""
        try:
            history = g.db_manager.get_user_search_history(
                g.current_user["user_id"], limit=50
            )

            return jsonify(
                {
                    "history": [query.to_dict() for query in history],
                    "total": len(history),
                }
            )

        except Exception as e:
            logger.error(f"Failed to get search history: {e}")
            raise

    # Repository management endpoints
    @app.route("/api/repos", methods=["GET"])
    @require_authentication
    def list_repositories():
        """List available repositories."""
        try:
            repos = g.db_manager.get_user_repositories(g.current_user["user_id"])

            return jsonify(
                {
                    "repositories": [repo.to_dict() for repo in repos],
                    "total": len(repos),
                }
            )

        except Exception as e:
            logger.error(f"Failed to list repositories: {e}")
            raise

    @app.route("/api/repos/<repo_id>/status", methods=["GET"])
    @require_authentication
    def get_repository_status(repo_id: str):
        """Get repository indexing status."""
        try:
            repo = g.db_manager.get_repository(repo_id)
            if not repo:
                raise NotFound("Repository not found")

            # Check if user has access to this repository
            if not g.db_manager.user_has_repo_access(
                g.current_user["user_id"], repo_id
            ):
                raise Forbidden("Access denied to this repository")

            status = g.db_manager.get_repository_status(repo_id)

            return jsonify(status)

        except (NotFound, Forbidden):
            raise
        except Exception as e:
            logger.error(f"Failed to get repository status: {e}")
            raise

    return app


def perform_semantic_search(query: str, limit: int) -> List[Dict[str, Any]]:
    """
    Perform semantic search on indexed code.

    Args:
        query: Search query string
        limit: Maximum number of results

    Returns:
        List of search results with relevance scores
    """
    # Mock semantic search results for testing
    mock_results = [
        {
            "file_path": "main.py",
            "function_name": "main",
            "line_number": 142,
            "code_snippet": "def main():\n    app = Application(args.config)\n    ...",
            "relevance_score": 0.95,
            "description": "Main application entry point",
        },
        {
            "file_path": "auth.py",
            "function_name": "authenticate_user",
            "line_number": 78,
            "code_snippet": "def authenticate_user(self, username: str, password: str):\n    ...",
            "relevance_score": 0.87,
            "description": "User authentication implementation",
        },
        {
            "file_path": "database.py",
            "function_name": "create_connection",
            "line_number": 45,
            "code_snippet": "def create_connection(self, connection_string: str):\n    ...",
            "relevance_score": 0.82,
            "description": "Database connection management",
        },
    ]

    # Filter and sort by relevance
    filtered_results = [
        r for r in mock_results if query.lower() in r["description"].lower()
    ]
    sorted_results = sorted(
        filtered_results, key=lambda x: x["relevance_score"], reverse=True
    )

    return sorted_results[:limit]


def generate_request_id() -> str:
    """Generate unique request ID for tracing."""
    import uuid

    return str(uuid.uuid4())[:8]
