"""
Search Error Formatter for standardized error responses.

Formats search timeout and size exceeded errors with actionable suggestions.
"""

from typing import Dict, Any, Optional


class SearchErrorFormatter:
    """
    Formats search errors with consistent structure and actionable suggestions.

    Only two error types per KISS principle:
    - SEARCH_TIMEOUT: Command exceeded timeout limit
    - RESULT_SIZE_EXCEEDED: Results exceed size limit
    """

    @staticmethod
    def format_timeout_error(
        timeout_seconds: int,
        partial_results: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Format timeout error response.

        Args:
            timeout_seconds: Configured timeout that was exceeded
            partial_results: Partial results captured before timeout (optional)

        Returns:
            Formatted error response dictionary
        """
        return {
            "error_code": "SEARCH_TIMEOUT",
            "message": f"Search exceeded {timeout_seconds}s timeout limit",
            "suggestion": "Try a more specific pattern or limit search scope to fewer files",
            "partial_results_available": partial_results is not None,
            "partial_results": partial_results,
        }

    @staticmethod
    def format_size_exceeded_error(
        actual_size_mb: float,
        limit_mb: int,
        truncated_results: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Format size exceeded error response.

        Args:
            actual_size_mb: Actual result size in megabytes
            limit_mb: Configured limit in megabytes
            truncated_results: Truncated results (first N bytes) (optional)

        Returns:
            Formatted error response dictionary
        """
        return {
            "error_code": "RESULT_SIZE_EXCEEDED",
            "message": f"Results ({actual_size_mb:.2f}MB) exceed {limit_mb}MB limit",
            "suggestion": "Refine search pattern to reduce matches, or increase result size limit in admin settings",
            "truncated_results_included": truncated_results is not None,
            "truncated_results": truncated_results,
        }
