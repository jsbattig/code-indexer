"""
Search Limits Validator for post-execution validation.

Validates search results against configured limits without pre-flight checks.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .search_result_file_manager import ParseResult
from ..models.search_limits_config import SearchLimitsConfig

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of search limits validation."""

    valid: bool
    error_code: Optional[str] = None
    message: Optional[str] = None
    content: Optional[str] = None


class SearchLimitsValidator:
    """
    Validates search execution results against configured limits.

    Performs post-execution validation only - no pre-flight repository
    size checks (following KISS principle from story spec).
    """

    def validate_result(
        self, parse_result: ParseResult, config: SearchLimitsConfig
    ) -> ValidationResult:
        """
        Validate parsed search result against configuration limits.

        Args:
            parse_result: Result from parsing search output file
            config: Search limits configuration

        Returns:
            ValidationResult indicating if limits were respected
        """
        if parse_result.exceeded:
            # Result size exceeded limit
            size_mb = parse_result.file_size / (1024 * 1024)
            limit_mb = config.max_result_size_mb

            return ValidationResult(
                valid=False,
                error_code="RESULT_SIZE_EXCEEDED",
                message=f"Search results ({size_mb:.2f}MB) exceed configured limit ({limit_mb}MB). "
                f"Refine your search pattern to reduce matches.",
            )

        # Result within limits
        return ValidationResult(valid=True, content=parse_result.content)
