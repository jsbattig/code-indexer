"""
Robust datetime parsing utilities for CIDX Server.

Handles various ISO 8601 datetime formats without hardcoded string replacements.
Provides better error handling and more explicit timezone handling.
"""

from datetime import datetime, timezone
import re


class DateTimeParseError(Exception):
    """Raised when datetime parsing fails."""

    pass


class DateTimeParser:
    """
    Robust datetime parser that handles various ISO 8601 formats.

    Supports:
    - Z suffix (Zulu time): "2024-01-01T12:30:45Z"
    - Timezone offsets: "2024-01-01T12:30:45+00:00", "2024-01-01T12:30:45-05:00"
    - With/without microseconds: "2024-01-01T12:30:45.123456Z"
    """

    # ISO 8601 datetime pattern with optional timezone
    ISO_DATETIME_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)"  # Date and time part
        r"(?:(Z)|([+-]\d{2}:\d{2}))?$"  # Optional timezone (Z or offset)
    )

    @classmethod
    def parse_iso_datetime(cls, datetime_str: str) -> datetime:
        """
        Parse ISO 8601 datetime string to timezone-aware datetime object.

        Args:
            datetime_str: ISO 8601 datetime string

        Returns:
            Timezone-aware datetime object

        Raises:
            DateTimeParseError: If string cannot be parsed
        """
        if not isinstance(datetime_str, str):
            raise DateTimeParseError(f"Expected string, got {type(datetime_str)}")

        # Clean the string
        datetime_str = datetime_str.strip()

        if not datetime_str:
            raise DateTimeParseError("Empty datetime string")

        # Check if string matches ISO 8601 pattern
        match = cls.ISO_DATETIME_PATTERN.match(datetime_str)
        if not match:
            raise DateTimeParseError(
                f"Invalid ISO 8601 datetime format: {datetime_str}"
            )

        base_datetime_str, z_suffix, offset = match.groups()

        try:
            if z_suffix:
                # Handle Z suffix (UTC)
                dt = datetime.fromisoformat(base_datetime_str)
                return dt.replace(tzinfo=timezone.utc)

            elif offset:
                # Handle timezone offset
                full_datetime_str = base_datetime_str + offset
                return datetime.fromisoformat(full_datetime_str)

            else:
                # No timezone specified, assume UTC for consistency
                dt = datetime.fromisoformat(base_datetime_str)
                return dt.replace(tzinfo=timezone.utc)

        except ValueError as e:
            raise DateTimeParseError(f"Failed to parse datetime '{datetime_str}': {e}")

    @classmethod
    def parse_user_datetime(cls, datetime_str: str) -> datetime:
        """
        Parse user datetime string using robust ISO parsing.

        Args:
            datetime_str: Datetime string to parse

        Returns:
            Timezone-aware datetime object

        Raises:
            DateTimeParseError: If parsing fails
        """
        return cls.parse_iso_datetime(datetime_str)

    @classmethod
    def format_for_storage(cls, dt: datetime) -> str:
        """
        Format datetime for storage in a consistent ISO format.

        Args:
            dt: Datetime object to format

        Returns:
            ISO 8601 formatted string with timezone
        """
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.isoformat()

    @classmethod
    def now_utc(cls) -> datetime:
        """
        Get current UTC datetime.

        Returns:
            Current UTC datetime with timezone info
        """
        return datetime.now(timezone.utc)
