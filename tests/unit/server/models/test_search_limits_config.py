"""
Unit tests for SearchLimitsConfig model.

Tests configuration model for search timeout and result size limits.
"""

import pytest
from pydantic import ValidationError

from code_indexer.server.models.search_limits_config import SearchLimitsConfig


class TestSearchLimitsConfig:
    """Test suite for SearchLimitsConfig model."""

    def test_create_with_defaults(self):
        """Test creating config with default values."""
        config = SearchLimitsConfig()

        assert config.max_result_size_mb == 1
        assert config.timeout_seconds == 30

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = SearchLimitsConfig(max_result_size_mb=10, timeout_seconds=60)

        assert config.max_result_size_mb == 10
        assert config.timeout_seconds == 60

    def test_max_result_size_within_range(self):
        """Test max_result_size_mb accepts values in valid range (1-100)."""
        config = SearchLimitsConfig(max_result_size_mb=50)
        assert config.max_result_size_mb == 50

        config = SearchLimitsConfig(max_result_size_mb=1)
        assert config.max_result_size_mb == 1

        config = SearchLimitsConfig(max_result_size_mb=100)
        assert config.max_result_size_mb == 100

    def test_max_result_size_below_minimum(self):
        """Test max_result_size_mb rejects values below minimum (1)."""
        with pytest.raises(ValidationError):
            SearchLimitsConfig(max_result_size_mb=0)

        with pytest.raises(ValidationError):
            SearchLimitsConfig(max_result_size_mb=-1)

    def test_max_result_size_above_maximum(self):
        """Test max_result_size_mb rejects values above maximum (100)."""
        with pytest.raises(ValidationError):
            SearchLimitsConfig(max_result_size_mb=101)

        with pytest.raises(ValidationError):
            SearchLimitsConfig(max_result_size_mb=1000)

    def test_timeout_seconds_within_range(self):
        """Test timeout_seconds accepts values in valid range (5-300)."""
        config = SearchLimitsConfig(timeout_seconds=150)
        assert config.timeout_seconds == 150

        config = SearchLimitsConfig(timeout_seconds=5)
        assert config.timeout_seconds == 5

        config = SearchLimitsConfig(timeout_seconds=300)
        assert config.timeout_seconds == 300

    def test_timeout_seconds_below_minimum(self):
        """Test timeout_seconds rejects values below minimum (5)."""
        with pytest.raises(ValidationError):
            SearchLimitsConfig(timeout_seconds=4)

        with pytest.raises(ValidationError):
            SearchLimitsConfig(timeout_seconds=0)

    def test_timeout_seconds_above_maximum(self):
        """Test timeout_seconds rejects values above maximum (300)."""
        with pytest.raises(ValidationError):
            SearchLimitsConfig(timeout_seconds=301)

        with pytest.raises(ValidationError):
            SearchLimitsConfig(timeout_seconds=600)

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = SearchLimitsConfig(max_result_size_mb=10, timeout_seconds=60)

        config_dict = config.to_dict()

        assert config_dict == {"max_result_size_mb": 10, "timeout_seconds": 60}

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {"max_result_size_mb": 25, "timeout_seconds": 120}

        config = SearchLimitsConfig.from_dict(data)

        assert config.max_result_size_mb == 25
        assert config.timeout_seconds == 120

    def test_from_dict_with_defaults(self):
        """Test creating config from empty dictionary uses defaults."""
        config = SearchLimitsConfig.from_dict({})

        assert config.max_result_size_mb == 1
        assert config.timeout_seconds == 30

    def test_max_size_bytes_property(self):
        """Test max_size_bytes property converts MB to bytes."""
        config = SearchLimitsConfig(max_result_size_mb=5)

        assert config.max_size_bytes == 5 * 1024 * 1024

    def test_model_serialization(self):
        """Test model can be serialized to JSON."""
        config = SearchLimitsConfig(max_result_size_mb=15, timeout_seconds=90)

        json_str = config.model_dump_json()

        assert "max_result_size_mb" in json_str
        assert "timeout_seconds" in json_str
        assert "15" in json_str
        assert "90" in json_str
