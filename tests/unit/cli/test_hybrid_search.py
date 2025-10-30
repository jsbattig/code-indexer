"""Unit tests for hybrid search mode detection and parameter routing.

This module tests the core logic for hybrid search (FTS + Semantic) including:
- Mode detection based on --fts and --semantic flags
- Parameter routing to appropriate search engines
- Graceful degradation when index missing
"""

from typing import Optional, Tuple


class TestHybridSearchModeDetection:
    """Test hybrid search mode detection logic."""

    def test_hybrid_mode_when_both_flags_set(self):
        """Test that mode is 'hybrid' when both --fts and --semantic flags are set."""
        # Arrange
        fts = True
        semantic = True

        # Act
        mode = self._determine_search_mode(fts, semantic)

        # Assert
        assert mode == "hybrid"

    def test_fts_mode_when_only_fts_flag_set(self):
        """Test that mode is 'fts' when only --fts flag is set."""
        # Arrange
        fts = True
        semantic = False

        # Act
        mode = self._determine_search_mode(fts, semantic)

        # Assert
        assert mode == "fts"

    def test_semantic_mode_when_no_flags_set(self):
        """Test that mode is 'semantic' (default) when no flags are set."""
        # Arrange
        fts = False
        semantic = False

        # Act
        mode = self._determine_search_mode(fts, semantic)

        # Assert
        assert mode == "semantic"

    def test_semantic_mode_when_only_semantic_flag_set(self):
        """Test that mode is 'semantic' when only --semantic flag is set."""
        # Arrange
        fts = False
        semantic = True

        # Act
        mode = self._determine_search_mode(fts, semantic)

        # Assert
        assert mode == "semantic"

    @staticmethod
    def _determine_search_mode(fts: bool, semantic: bool) -> str:
        """Helper to test mode detection logic.

        This will be the actual implementation in cli.py.
        """
        if fts and semantic:
            return "hybrid"
        elif fts:
            return "fts"
        else:
            return "semantic"


class TestParameterRouting:
    """Test parameter routing to FTS and semantic search engines."""

    def test_common_parameters_routed_to_both(self):
        """Test that common parameters (limit, language, path_filter) are routed to both searches."""
        # Arrange
        kwargs = {
            "limit": 20,
            "languages": ("python",),
            "path_filter": "*/src/*",
            "case_sensitive": True,
            "min_score": 0.8,
        }

        # Act
        fts_params, semantic_params = self._route_search_parameters(kwargs)

        # Assert - common params in both
        assert fts_params["limit"] == 20
        assert semantic_params["limit"] == 20
        assert fts_params["language_filter"] == "python"
        assert semantic_params["languages"] == ("python",)
        assert fts_params["path_filter"] == "*/src/*"
        assert semantic_params["path_filter"] == "*/src/*"

    def test_fts_specific_parameters_only_in_fts(self):
        """Test that FTS-specific parameters are only in FTS params."""
        # Arrange
        kwargs = {
            "limit": 10,
            "case_sensitive": True,
            "edit_distance": 2,
            "snippet_lines": 5,
            "min_score": 0.8,
        }

        # Act
        fts_params, semantic_params = self._route_search_parameters(kwargs)

        # Assert - FTS-specific params only in fts_params
        assert fts_params["case_sensitive"] is True
        assert fts_params["edit_distance"] == 2
        assert fts_params["snippet_lines"] == 5
        assert "case_sensitive" not in semantic_params
        assert "edit_distance" not in semantic_params
        assert "snippet_lines" not in semantic_params

    def test_semantic_specific_parameters_only_in_semantic(self):
        """Test that semantic-specific parameters are only in semantic params."""
        # Arrange
        kwargs = {
            "limit": 10,
            "min_score": 0.8,
            "accuracy": "high",
            "case_sensitive": False,
        }

        # Act
        fts_params, semantic_params = self._route_search_parameters(kwargs)

        # Assert - semantic-specific params only in semantic_params
        assert semantic_params["min_score"] == 0.8
        assert semantic_params["accuracy"] == "high"
        assert "min_score" not in fts_params
        assert "accuracy" not in fts_params

    def test_default_values_when_parameters_missing(self):
        """Test that default values are used when parameters are not provided."""
        # Arrange
        kwargs = {
            "limit": 10,
        }

        # Act
        fts_params, semantic_params = self._route_search_parameters(kwargs)

        # Assert - defaults
        assert fts_params["limit"] == 10
        assert fts_params["case_sensitive"] is False
        assert fts_params["edit_distance"] == 0
        assert fts_params["snippet_lines"] == 5
        assert semantic_params["limit"] == 10
        assert semantic_params["accuracy"] == "balanced"

    @staticmethod
    def _route_search_parameters(kwargs: dict) -> Tuple[dict, dict]:
        """Helper to test parameter routing logic.

        This will be the actual implementation in cli.py.
        """
        # Common parameters (apply to both)
        common_params = {
            "limit": kwargs.get("limit", 10),
            "path_filter": kwargs.get("path_filter"),
        }

        # FTS-specific parameters
        fts_params = {
            **common_params,
            "case_sensitive": kwargs.get("case_sensitive", False),
            "edit_distance": kwargs.get("edit_distance", 0),
            "snippet_lines": kwargs.get("snippet_lines", 5),
        }

        # Handle languages - FTS takes first language only
        languages = kwargs.get("languages", ())
        if languages:
            fts_params["language_filter"] = languages[0]
        else:
            fts_params["language_filter"] = None

        # Semantic-specific parameters
        semantic_params = {
            **common_params,
            "min_score": kwargs.get("min_score"),
            "accuracy": kwargs.get("accuracy", "balanced"),
        }

        # Semantic takes all languages
        semantic_params["languages"] = languages

        return fts_params, semantic_params


class TestGracefulDegradation:
    """Test graceful degradation when FTS index is missing."""

    def test_hybrid_falls_back_to_semantic_when_fts_missing(self):
        """Test that hybrid mode falls back to semantic when FTS index is missing."""
        # Arrange
        mode = "hybrid"
        has_fts = False
        has_semantic = True

        # Act
        adjusted_mode, warning = self._adjust_mode_for_availability(
            mode, has_fts, has_semantic
        )

        # Assert
        assert adjusted_mode == "semantic"
        assert "FTS index not available" in warning
        assert "falling back to semantic" in warning.lower()

    def test_fts_only_fails_when_fts_missing(self):
        """Test that FTS-only mode returns error when FTS index is missing."""
        # Arrange
        mode = "fts"
        has_fts = False
        has_semantic = True

        # Act
        adjusted_mode, message = self._adjust_mode_for_availability(
            mode, has_fts, has_semantic
        )

        # Assert
        assert adjusted_mode is None
        assert "FTS index not found" in message
        assert "cidx index --fts" in message

    def test_semantic_only_fails_when_semantic_missing(self):
        """Test that semantic mode returns error when semantic index is missing."""
        # Arrange
        mode = "semantic"
        has_fts = False
        has_semantic = False

        # Act
        adjusted_mode, message = self._adjust_mode_for_availability(
            mode, has_fts, has_semantic
        )

        # Assert
        assert adjusted_mode is None
        assert "Semantic index not found" in message
        assert "cidx index" in message

    def test_no_adjustment_when_all_indexes_available(self):
        """Test that no adjustment happens when all required indexes are available."""
        # Arrange
        mode = "hybrid"
        has_fts = True
        has_semantic = True

        # Act
        adjusted_mode, message = self._adjust_mode_for_availability(
            mode, has_fts, has_semantic
        )

        # Assert
        assert adjusted_mode == "hybrid"
        assert message is None

    @staticmethod
    def _adjust_mode_for_availability(
        mode: str, has_fts: bool, has_semantic: bool
    ) -> Tuple[Optional[str], Optional[str]]:
        """Helper to test graceful degradation logic.

        Returns:
            (adjusted_mode, warning_or_error_message)
            adjusted_mode is None if mode cannot be satisfied
        """
        if mode == "hybrid":
            if not has_fts and has_semantic:
                return (
                    "semantic",
                    "Warning: FTS index not available, falling back to semantic-only",
                )
            elif not has_semantic:
                return None, "Error: Semantic index not found. Run 'cidx index' first."
            else:
                return mode, None

        elif mode == "fts":
            if not has_fts:
                return None, "Error: FTS index not found. Run 'cidx index --fts' first."
            else:
                return mode, None

        else:  # semantic
            if not has_semantic:
                return None, "Error: Semantic index not found. Run 'cidx index' first."
            else:
                return mode, None
