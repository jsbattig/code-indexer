"""
Middleware modules for the CIDX server.

Contains middleware components for request/response processing.
"""

from .error_handler import GlobalErrorHandler

__all__ = ["GlobalErrorHandler"]
