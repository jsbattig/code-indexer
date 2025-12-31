"""
Unit tests for FileContentLimitsConfig model.

Tests configuration model for file content token limits and character-to-token ratios.
"""

import pytest
from pydantic import ValidationError

from code_indexer.server.models.file_content_limits_config import (
    FileContentLimitsConfig,
)


class TestFileContentLimitsConfig:
    """Test suite for FileContentLimitsConfig model."""

    def test_create_with_defaults(self):
        """Test creating config with default values."""
        config = FileContentLimitsConfig()

        assert config.max_tokens_per_request == 5000
        assert config.chars_per_token == 4

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = FileContentLimitsConfig(
            max_tokens_per_request=10000, chars_per_token=4
        )

        assert config.max_tokens_per_request == 10000
        assert config.chars_per_token == 4

    def test_max_tokens_within_range(self):
        """Test max_tokens_per_request accepts values in valid range (1000-20000)."""
        config = FileContentLimitsConfig(max_tokens_per_request=10000)
        assert config.max_tokens_per_request == 10000

        config = FileContentLimitsConfig(max_tokens_per_request=1000)
        assert config.max_tokens_per_request == 1000

        config = FileContentLimitsConfig(max_tokens_per_request=20000)
        assert config.max_tokens_per_request == 20000

    def test_max_tokens_below_minimum(self):
        """Test max_tokens_per_request rejects values below minimum (1000)."""
        with pytest.raises(ValidationError):
            FileContentLimitsConfig(max_tokens_per_request=999)

        with pytest.raises(ValidationError):
            FileContentLimitsConfig(max_tokens_per_request=0)

    def test_max_tokens_above_maximum(self):
        """Test max_tokens_per_request rejects values above maximum (20000)."""
        with pytest.raises(ValidationError):
            FileContentLimitsConfig(max_tokens_per_request=20001)

        with pytest.raises(ValidationError):
            FileContentLimitsConfig(max_tokens_per_request=50000)

    def test_chars_per_token_within_range(self):
        """Test chars_per_token accepts values in valid range (3-5)."""
        config = FileContentLimitsConfig(chars_per_token=4)
        assert config.chars_per_token == 4

        config = FileContentLimitsConfig(chars_per_token=3)
        assert config.chars_per_token == 3

        config = FileContentLimitsConfig(chars_per_token=5)
        assert config.chars_per_token == 5

    def test_chars_per_token_below_minimum(self):
        """Test chars_per_token rejects values below minimum (3)."""
        with pytest.raises(ValidationError):
            FileContentLimitsConfig(chars_per_token=2)

        with pytest.raises(ValidationError):
            FileContentLimitsConfig(chars_per_token=0)

    def test_chars_per_token_above_maximum(self):
        """Test chars_per_token rejects values above maximum (5)."""
        with pytest.raises(ValidationError):
            FileContentLimitsConfig(chars_per_token=6)

        with pytest.raises(ValidationError):
            FileContentLimitsConfig(chars_per_token=10)

    def test_max_chars_per_request_property(self):
        """Test max_chars_per_request property calculates correctly."""
        config = FileContentLimitsConfig(max_tokens_per_request=5000, chars_per_token=4)
        assert config.max_chars_per_request == 20000

        config = FileContentLimitsConfig(
            max_tokens_per_request=10000, chars_per_token=3
        )
        assert config.max_chars_per_request == 30000

        config = FileContentLimitsConfig(max_tokens_per_request=2000, chars_per_token=5)
        assert config.max_chars_per_request == 10000

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = FileContentLimitsConfig(
            max_tokens_per_request=10000, chars_per_token=4
        )

        config_dict = config.to_dict()

        assert config_dict == {"max_tokens_per_request": 10000, "chars_per_token": 4}

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {"max_tokens_per_request": 15000, "chars_per_token": 3}

        config = FileContentLimitsConfig.from_dict(data)

        assert config.max_tokens_per_request == 15000
        assert config.chars_per_token == 3

    def test_from_dict_with_defaults(self):
        """Test creating config from empty dictionary uses defaults."""
        config = FileContentLimitsConfig.from_dict({})

        assert config.max_tokens_per_request == 5000
        assert config.chars_per_token == 4

    def test_model_serialization(self):
        """Test model can be serialized to JSON."""
        config = FileContentLimitsConfig(max_tokens_per_request=8000, chars_per_token=4)

        json_str = config.model_dump_json()

        assert "max_tokens_per_request" in json_str
        assert "chars_per_token" in json_str
        assert "8000" in json_str
        assert "4" in json_str
