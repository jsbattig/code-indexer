"""Tests for configuration management."""

from pathlib import Path
import pytest

from code_indexer.config import Config, ConfigManager, OllamaConfig, QdrantConfig
from .conftest import local_temporary_directory


def test_default_config():
    """Test default configuration values."""
    config = Config()

    assert config.codebase_dir == Path(".")
    assert "py" in config.file_extensions
    assert "js" in config.file_extensions
    assert "node_modules" in config.exclude_dirs
    assert config.ollama.model == "nomic-embed-text"
    assert config.qdrant.vector_size == 768


def test_config_validation():
    """Test configuration validation."""
    # Test path conversion
    config = Config(codebase_dir="/tmp")
    assert config.codebase_dir == Path("/tmp")

    # Test extension normalization
    config = Config(file_extensions=[".py", "js", ".ts"])
    assert config.file_extensions == ["py", "js", "ts"]


def test_config_manager_save_load():
    """Test saving and loading configuration."""
    with local_temporary_directory() as tmpdir:
        config_path = Path(tmpdir) / "test_config.json"
        manager = ConfigManager(config_path)

        # Create and save config
        original_config = Config(
            codebase_dir=Path("/test"),
            file_extensions=["py", "js"],
            ollama=OllamaConfig(model="test-model"),
        )

        manager._config = original_config
        manager.save()

        # Load and verify
        loaded_config = manager.load()

        assert loaded_config.codebase_dir == Path("/test")
        assert loaded_config.file_extensions == ["py", "js"]
        assert loaded_config.ollama.model == "test-model"


def test_config_manager_update():
    """Test updating configuration."""
    with local_temporary_directory() as tmpdir:
        config_path = Path(tmpdir) / "test_config.json"
        manager = ConfigManager(config_path)

        # Create initial config
        manager.create_default_config()

        # Update config
        updated_config = manager.update_config(
            file_extensions=["py", "rs"], ollama={"model": "new-model"}
        )

        assert updated_config.file_extensions == ["py", "rs"]
        assert updated_config.ollama.model == "new-model"

        # Verify it was saved
        reloaded_config = manager.load()
        assert reloaded_config.file_extensions == ["py", "rs"]
        assert reloaded_config.ollama.model == "new-model"


def test_qdrant_config_default_segment_size():
    """Test QdrantConfig has default max_segment_size_kb of 102400 (100MB)."""
    qdrant_config = QdrantConfig()
    assert qdrant_config.max_segment_size_kb == 102400


def test_qdrant_config_segment_size_validation():
    """Test QdrantConfig validates segment size is positive."""
    # Valid positive values should work
    valid_config = QdrantConfig(max_segment_size_kb=51200)  # 50MB
    assert valid_config.max_segment_size_kb == 51200

    # Zero should be rejected
    with pytest.raises(ValueError, match="Segment size must be positive"):
        QdrantConfig(max_segment_size_kb=0)

    # Negative values should be rejected
    with pytest.raises(ValueError, match="Segment size must be positive"):
        QdrantConfig(max_segment_size_kb=-1024)


def test_qdrant_config_segment_size_field_type():
    """Test QdrantConfig max_segment_size_kb field accepts integers."""
    config = QdrantConfig(max_segment_size_kb=204800)  # 200MB
    assert isinstance(config.max_segment_size_kb, int)
    assert config.max_segment_size_kb == 204800


def test_config_with_qdrant_segment_size():
    """Test Config includes QdrantConfig with max_segment_size_kb field."""
    config = Config()
    assert hasattr(config.qdrant, "max_segment_size_kb")
    assert config.qdrant.max_segment_size_kb == 102400
