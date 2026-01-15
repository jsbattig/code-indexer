"""
Unit tests for routes.py payload cache validation.

Story #679: Add Payload Cache Settings to Web UI Config Screen

Tests that _validate_config_section properly validates payload cache fields.
"""

# Import the validation function
from code_indexer.server.web.routes import _validate_config_section


class TestPayloadCacheValidation:
    """Tests for payload cache field validation in routes.py."""

    def test_validate_payload_preview_size_chars_valid(self):
        """Test that valid payload_preview_size_chars passes validation."""
        data = {"payload_preview_size_chars": "2000"}
        error = _validate_config_section("cache", data)
        assert error is None

    def test_validate_payload_preview_size_chars_invalid_not_number(self):
        """Test that non-numeric payload_preview_size_chars fails validation."""
        data = {"payload_preview_size_chars": "invalid"}
        error = _validate_config_section("cache", data)
        assert error is not None
        assert "valid number" in error.lower() or "must be" in error.lower()

    def test_validate_payload_preview_size_chars_invalid_zero(self):
        """Test that zero payload_preview_size_chars fails validation."""
        data = {"payload_preview_size_chars": "0"}
        error = _validate_config_section("cache", data)
        assert error is not None
        assert "positive" in error.lower() or "must be" in error.lower()

    def test_validate_payload_preview_size_chars_invalid_negative(self):
        """Test that negative payload_preview_size_chars fails validation."""
        data = {"payload_preview_size_chars": "-100"}
        error = _validate_config_section("cache", data)
        assert error is not None
        assert "positive" in error.lower() or "must be" in error.lower()

    def test_validate_payload_max_fetch_size_chars_valid(self):
        """Test that valid payload_max_fetch_size_chars passes validation."""
        data = {"payload_max_fetch_size_chars": "5000"}
        error = _validate_config_section("cache", data)
        assert error is None

    def test_validate_payload_max_fetch_size_chars_invalid_not_number(self):
        """Test that non-numeric payload_max_fetch_size_chars fails validation."""
        data = {"payload_max_fetch_size_chars": "invalid"}
        error = _validate_config_section("cache", data)
        assert error is not None
        assert "valid number" in error.lower() or "must be" in error.lower()

    def test_validate_payload_cache_ttl_seconds_valid(self):
        """Test that valid payload_cache_ttl_seconds passes validation."""
        data = {"payload_cache_ttl_seconds": "900"}
        error = _validate_config_section("cache", data)
        assert error is None

    def test_validate_payload_cache_ttl_seconds_invalid_not_number(self):
        """Test that non-numeric payload_cache_ttl_seconds fails validation."""
        data = {"payload_cache_ttl_seconds": "invalid"}
        error = _validate_config_section("cache", data)
        assert error is not None
        assert "valid number" in error.lower() or "must be" in error.lower()

    def test_validate_payload_cleanup_interval_seconds_valid(self):
        """Test that valid payload_cleanup_interval_seconds passes validation."""
        data = {"payload_cleanup_interval_seconds": "60"}
        error = _validate_config_section("cache", data)
        assert error is None

    def test_validate_payload_cleanup_interval_seconds_invalid_not_number(self):
        """Test that non-numeric payload_cleanup_interval_seconds fails validation."""
        data = {"payload_cleanup_interval_seconds": "invalid"}
        error = _validate_config_section("cache", data)
        assert error is not None
        assert "valid number" in error.lower() or "must be" in error.lower()

    def test_validate_all_payload_fields_valid(self):
        """Test that all payload cache fields pass validation together."""
        data = {
            "payload_preview_size_chars": "3000",
            "payload_max_fetch_size_chars": "8000",
            "payload_cache_ttl_seconds": "1800",
            "payload_cleanup_interval_seconds": "120",
        }
        error = _validate_config_section("cache", data)
        assert error is None

    def test_validate_payload_fields_with_existing_cache_fields(self):
        """Test that payload fields validate alongside existing cache fields."""
        data = {
            "index_cache_ttl_minutes": "10",
            "fts_cache_ttl_minutes": "10",
            "payload_preview_size_chars": "2000",
            "payload_max_fetch_size_chars": "5000",
        }
        error = _validate_config_section("cache", data)
        assert error is None
