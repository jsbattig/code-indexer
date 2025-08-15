"""Tests for QdrantConfig payload index configuration (Story 2)."""

import pytest

from code_indexer.config import QdrantConfig


class TestQdrantConfigPayloadIndexes:
    """Test payload index configuration fields in QdrantConfig."""

    def test_enable_payload_indexes_default_value(self):
        """Test that enable_payload_indexes defaults to True."""
        config = QdrantConfig()

        # This will fail until we add the field
        assert hasattr(config, "enable_payload_indexes")
        assert config.enable_payload_indexes is True

    def test_enable_payload_indexes_can_be_disabled(self):
        """Test that enable_payload_indexes can be set to False."""
        config = QdrantConfig(enable_payload_indexes=False)

        assert config.enable_payload_indexes is False

    def test_payload_indexes_default_value(self):
        """Test that payload_indexes has correct default values."""
        config = QdrantConfig()

        # This will fail until we add the field
        assert hasattr(config, "payload_indexes")
        assert isinstance(config.payload_indexes, list)

        expected_defaults = [
            ("type", "keyword"),
            ("path", "text"),
            ("git_branch", "keyword"),
            ("file_mtime", "integer"),
            ("hidden_branches", "keyword"),
        ]

        assert config.payload_indexes == expected_defaults

    def test_payload_indexes_custom_configuration(self):
        """Test that payload_indexes can be customized."""
        custom_indexes = [
            ("custom_field", "keyword"),
            ("another_field", "text"),
        ]

        config = QdrantConfig(payload_indexes=custom_indexes)

        assert config.payload_indexes == custom_indexes

    def test_payload_indexes_field_validation_valid_schemas(self):
        """Test that valid field schemas are accepted."""
        valid_schemas = ["keyword", "text", "integer", "geo", "bool"]

        for schema_type in valid_schemas:
            payload_indexes = [("test_field", schema_type)]
            config = QdrantConfig(payload_indexes=payload_indexes)
            assert config.payload_indexes == payload_indexes

    def test_payload_indexes_field_validation_invalid_schema(self):
        """Test that invalid field schemas are rejected."""
        invalid_payload_indexes = [
            ("test_field", "invalid_schema"),
        ]

        with pytest.raises(
            ValueError,
            match="Invalid field_schema 'invalid_schema' for field 'test_field'",
        ):
            QdrantConfig(payload_indexes=invalid_payload_indexes)

    def test_payload_indexes_field_validation_multiple_fields(self):
        """Test validation with multiple fields, some valid, some invalid."""
        mixed_payload_indexes = [
            ("valid_field", "keyword"),
            ("invalid_field", "not_valid"),
        ]

        with pytest.raises(
            ValueError,
            match="Invalid field_schema 'not_valid' for field 'invalid_field'",
        ):
            QdrantConfig(payload_indexes=mixed_payload_indexes)

    def test_payload_indexes_empty_list(self):
        """Test that empty payload_indexes list is allowed."""
        config = QdrantConfig(payload_indexes=[])

        assert config.payload_indexes == []

    def test_enable_payload_indexes_field_description(self):
        """Test that enable_payload_indexes field has memory impact warning in description."""
        config = QdrantConfig()

        # Access the field info to check description
        field_info = config.model_fields["enable_payload_indexes"]
        description = field_info.description

        # Should contain memory impact warning
        assert "100-300MB additional RAM" in description

    def test_payload_indexes_field_description(self):
        """Test that payload_indexes field has proper description."""
        config = QdrantConfig()

        field_info = config.model_fields["payload_indexes"]
        description = field_info.description

        assert "field_name, field_schema" in description
        assert "tuples" in description

    def test_backward_compatibility_existing_config(self):
        """Test that existing QdrantConfig instances still work without new fields."""
        # Test that we can create a config with just the existing fields
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=768,
            hnsw_ef=64,
            hnsw_ef_construct=200,
            hnsw_m=32,
            max_segment_size_kb=102400,
        )

        # New fields should have default values
        assert config.enable_payload_indexes is True
        assert len(config.payload_indexes) == 5  # Default 5 indexes

    def test_config_serialization_with_new_fields(self):
        """Test that config with new fields can be serialized and deserialized."""
        original_config = QdrantConfig(
            enable_payload_indexes=False,
            payload_indexes=[("custom", "keyword"), ("field", "text")],
        )

        # Test model_dump (serialization)
        config_dict = original_config.model_dump()

        assert config_dict["enable_payload_indexes"] is False
        assert config_dict["payload_indexes"] == [
            ("custom", "keyword"),
            ("field", "text"),
        ]

        # Test reconstruction from dict
        reconstructed_config = QdrantConfig(**config_dict)

        assert reconstructed_config.enable_payload_indexes is False
        assert reconstructed_config.payload_indexes == [
            ("custom", "keyword"),
            ("field", "text"),
        ]
