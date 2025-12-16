"""Unit tests for SCIP CLI compact output formatting."""

import pytest
from unittest.mock import Mock, patch
import click.testing


@pytest.fixture
def mock_scip_environment(tmp_path, monkeypatch):
    """Setup mock SCIP environment with necessary files and mocks."""
    # Create .code-indexer/scip directory
    scip_dir = tmp_path / ".code-indexer" / "scip"
    scip_dir.mkdir(parents=True)
    scip_file = scip_dir / "test.scip"
    scip_file.touch()

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    return {
        "scip_dir": scip_dir,
        "scip_file": scip_file,
        "tmp_path": tmp_path,
    }


class TestReferencesCompactOutput:
    """Test compact output format for 'cidx scip references' command."""

    def test_references_command_produces_one_line_per_result(
        self, mock_scip_environment
    ):
        """Test that references command outputs exactly one line per result."""
        # Create mock result with SCIP symbol
        mock_result = Mock()
        mock_result.symbol = (
            "scip-python python code-indexer abc123 `auth`/authenticate()."
        )
        mock_result.file_path = "src/auth.py"
        mock_result.line = 45
        mock_result.column = 10

        # Mock the query engine (imported inside function)
        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.find_references.return_value = [mock_result]
            mock_engine_cls.return_value = mock_engine

            # Mock StatusTracker (imported inside function)
            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                # Invoke the command
                from code_indexer.cli_scip import scip_references

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_references, ["authenticate"])

                # Verify output format
                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Find the result line (should contain file path and symbol)
                result_lines = [line for line in lines if "src/auth.py" in line]
                assert len(result_lines) >= 1, "Should have at least one result line"

                # The result line should be compact: "display_name (file:line)"
                # It should NOT have a separate "Symbol:" line
                result_line = result_lines[0]
                assert "auth/authenticate()" in result_line
                assert "src/auth.py:45" in result_line

                # Verify no separate "Symbol:" line follows
                symbol_lines = [line for line in lines if "Symbol:" in line]
                assert (
                    len(symbol_lines) == 0
                ), "Should NOT have separate 'Symbol:' lines"

    def test_references_uses_extract_display_name_helper(self):
        """Test that _extract_display_name() correctly formats SCIP symbols."""
        from code_indexer.cli_scip import _extract_display_name

        test_cases = [
            (
                "scip-python python code-indexer abc123 `auth`/authenticate().",
                "auth/authenticate().",
            ),
            (
                "scip-python python code-indexer abc123 `db`/UserRepo#save().",
                "db/UserRepo#save().",
            ),
            (
                "scip-python python code-indexer abc123 `module.submodule`/ClassName#method().",
                "module.submodule/ClassName#method().",
            ),
        ]

        for full_symbol, expected_display in test_cases:
            actual = _extract_display_name(full_symbol)
            assert actual == expected_display, f"Failed for {full_symbol}"

    def test_references_multiple_results_each_one_line(self, mock_scip_environment):
        """Test that multiple results each get exactly one line."""
        # Create multiple mock results
        mock_results = [
            Mock(
                symbol="scip-python python code-indexer abc123 `auth`/authenticate().",
                file_path="src/auth.py",
                line=45,
                column=10,
            ),
            Mock(
                symbol="scip-python python code-indexer abc123 `auth`/validate().",
                file_path="src/auth.py",
                line=67,
                column=5,
            ),
        ]

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.find_references.return_value = mock_results
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_references

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_references, ["auth"])

                assert result.exit_code == 0

                # Count result lines (lines containing file paths)
                lines = result.output.strip().split("\n")
                result_lines = [line for line in lines if "src/auth.py:" in line]

                # Should have exactly 2 result lines (one per mock result)
                assert len(result_lines) == 2

                # No "Symbol:" lines
                symbol_lines = [line for line in lines if "Symbol:" in line]
                assert len(symbol_lines) == 0


class TestDependenciesCompactOutput:
    """Test compact output format for 'cidx scip dependencies' command."""

    def test_dependencies_command_produces_flat_one_line_per_result(
        self, mock_scip_environment
    ):
        """Test that dependencies command outputs flat list with one line per result."""
        mock_result = Mock()
        mock_result.symbol = (
            "scip-python python code-indexer abc123 `db`/UserRepo#save()."
        )
        mock_result.file_path = "src/db/user_repo.py"
        mock_result.line = 67
        mock_result.relationship = "reference"

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.get_dependencies.return_value = [mock_result]
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_dependencies

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_dependencies, ["UserService"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Find result line
                result_lines = [line for line in lines if "src/db/user_repo.py" in line]
                assert len(result_lines) >= 1

                # Should contain display name, file path, and relationship
                result_line = result_lines[0]
                assert "db/UserRepo#save()." in result_line
                assert "src/db/user_repo.py:67" in result_line
                assert "[reference]" in result_line

    def test_dependencies_no_grouping_by_symbol(self, mock_scip_environment):
        """Test that dependencies output is flat, not grouped by symbol."""
        mock_results = [
            Mock(
                symbol="scip-python python code-indexer abc123 `db`/UserRepo#save().",
                file_path="src/db/user_repo.py",
                line=67,
                relationship="reference",
            ),
            Mock(
                symbol="scip-python python code-indexer abc123 `db`/UserRepo#save().",
                file_path="src/services/user_service.py",
                line=123,
                relationship="reference",
            ),
        ]

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.get_dependencies.return_value = mock_results
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_dependencies

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_dependencies, ["UserService"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Should NOT have "... and X more" grouping text
                grouping_lines = [
                    line for line in lines if "and" in line and "more" in line
                ]
                assert len(grouping_lines) == 0

                # Should have 2 distinct result lines
                result_lines = [line for line in lines if "db/UserRepo#save()." in line]
                assert len(result_lines) == 2


class TestDependentsCompactOutput:
    """Test compact output format for 'cidx scip dependents' command."""

    def test_dependents_command_produces_flat_one_line_per_result(
        self, mock_scip_environment
    ):
        """Test that dependents command outputs flat list with one line per result."""
        mock_result = Mock()
        mock_result.symbol = (
            "scip-python python code-indexer abc123 `services`/UserService#create()."
        )
        mock_result.file_path = "src/services/user_service.py"
        mock_result.line = 89
        mock_result.relationship = "call"

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.get_dependents.return_value = [mock_result]
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_dependents

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_dependents, ["UserRepo"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Find result line
                result_lines = [
                    line for line in lines if "src/services/user_service.py" in line
                ]
                assert len(result_lines) >= 1

                # Should contain display name, file path, and relationship
                result_line = result_lines[0]
                assert "services/UserService#create()." in result_line
                assert "src/services/user_service.py:89" in result_line
                assert "[call]" in result_line

    def test_dependents_no_grouping_by_symbol(self, mock_scip_environment):
        """Test that dependents output is flat, not grouped by symbol."""
        mock_results = [
            Mock(
                symbol="scip-python python code-indexer abc123 `services`/UserService#create().",
                file_path="src/services/user_service.py",
                line=89,
                relationship="call",
            ),
            Mock(
                symbol="scip-python python code-indexer abc123 `services`/UserService#update().",
                file_path="src/services/user_service.py",
                line=145,
                relationship="call",
            ),
        ]

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.get_dependents.return_value = mock_results
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_dependents

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_dependents, ["UserRepo"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Should NOT have "... and X more" grouping text
                grouping_lines = [
                    line for line in lines if "and" in line and "more" in line
                ]
                assert len(grouping_lines) == 0

                # Should have 2 distinct result lines
                result_lines = [
                    line for line in lines if "services/UserService#" in line
                ]
                assert len(result_lines) == 2


class TestImpactCompactOutput:
    """Test compact output format for 'cidx scip impact' command."""

    def test_impact_command_produces_one_line_per_result_with_depth(
        self, mock_scip_environment
    ):
        """Test that impact command outputs one line per result with depth indicator."""
        mock_result = Mock()
        mock_result.symbol = (
            "scip-python python code-indexer abc123 `auth`/authenticate()."
        )
        mock_result.file_path = "src/auth.py"
        mock_result.line = 45
        mock_result.depth = 1

        mock_impact_result = Mock()
        mock_impact_result.total_affected = 1
        mock_impact_result.affected_files = [Mock(path="src/auth.py")]
        mock_impact_result.affected_symbols = [mock_result]

        with patch("code_indexer.scip.query.composites.analyze_impact") as mock_analyze:
            mock_analyze.return_value = mock_impact_result

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_impact

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_impact, ["validate_token"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Find result line
                result_lines = [line for line in lines if "src/auth.py" in line]
                assert len(result_lines) >= 1

                # Should contain depth indicator, display name, and file path
                result_line = result_lines[0]
                assert "[depth 1]" in result_line
                assert "auth/authenticate()." in result_line
                assert "src/auth.py:45" in result_line

    def test_impact_flattened_no_depth_grouping(self, mock_scip_environment):
        """Test that impact output is flat, not grouped by depth."""
        mock_results = [
            Mock(
                symbol="scip-python python code-indexer abc123 `auth`/authenticate().",
                file_path="src/auth.py",
                line=45,
                depth=1,
            ),
            Mock(
                symbol="scip-python python code-indexer abc123 `services`/UserService#login().",
                file_path="src/services/user_service.py",
                line=89,
                depth=2,
            ),
        ]

        mock_impact_result = Mock()
        mock_impact_result.total_affected = 2
        mock_impact_result.affected_files = [
            Mock(path="src/auth.py"),
            Mock(path="src/services/user_service.py"),
        ]
        mock_impact_result.affected_symbols = mock_results

        with patch("code_indexer.scip.query.composites.analyze_impact") as mock_analyze:
            mock_analyze.return_value = mock_impact_result

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_impact

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_impact, ["validate_token"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Should have 2 result lines with different depths
                depth1_lines = [line for line in lines if "[depth 1]" in line]
                depth2_lines = [line for line in lines if "[depth 2]" in line]

                assert len(depth1_lines) == 1
                assert len(depth2_lines) == 1


class TestContextCompactOutput:
    """Test compact output format for 'cidx scip context' command."""

    def test_context_command_produces_one_line_per_result(self, mock_scip_environment):
        """Test that context command outputs one line per result with score."""
        mock_symbol = Mock()
        mock_symbol.symbol = (
            "scip-python python code-indexer abc123 `auth`/authenticate()."
        )
        mock_symbol.line = 45
        mock_symbol.role = "definition"

        mock_file = Mock()
        mock_file.path = "src/auth.py"
        mock_file.relevance_score = 0.95
        mock_file.symbols = [mock_symbol]

        mock_context_result = Mock()
        mock_context_result.total_symbols = 1
        mock_context_result.total_files = 1
        mock_context_result.files = [mock_file]

        with patch(
            "code_indexer.scip.query.composites.get_smart_context"
        ) as mock_get_context:
            mock_get_context.return_value = mock_context_result

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_context

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_context, ["validate_token"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Find result line
                result_lines = [line for line in lines if "src/auth.py" in line]
                assert len(result_lines) >= 1

                # Should contain role indicator, display name, file path, and score
                result_line = result_lines[0]
                assert "[def]" in result_line
                assert "auth/authenticate()." in result_line
                assert "src/auth.py:45" in result_line
                assert "score:" in result_line

    def test_context_flattened_no_file_grouping(self, mock_scip_environment):
        """Test that context output is flat, not grouped by file."""
        mock_symbols = [
            Mock(
                symbol="scip-python python code-indexer abc123 `auth`/authenticate().",
                line=45,
                role="definition",
            ),
            Mock(
                symbol="scip-python python code-indexer abc123 `auth`/validate_token().",
                line=67,
                role="reference",
            ),
        ]

        mock_file = Mock()
        mock_file.path = "src/auth.py"
        mock_file.relevance_score = 0.95
        mock_file.symbols = mock_symbols

        mock_context_result = Mock()
        mock_context_result.total_symbols = 2
        mock_context_result.total_files = 1
        mock_context_result.files = [mock_file]

        with patch(
            "code_indexer.scip.query.composites.get_smart_context"
        ) as mock_get_context:
            mock_get_context.return_value = mock_context_result

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_context

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_context, ["validate_token"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Should have 2 distinct result lines
                result_lines = [line for line in lines if "src/auth.py:" in line]
                assert len(result_lines) == 2

                # Verify different roles and scores
                def_lines = [line for line in lines if "[def]" in line]
                ref_lines = [line for line in lines if "[ref]" in line]

                assert len(def_lines) == 1
                assert len(ref_lines) == 1

    def test_context_uses_extract_display_name_on_symbol_name(
        self, mock_scip_environment
    ):
        """Test that context command calls _extract_display_name() on sym.name field.

        Bug #2: context command shows verbose SCIP prefixes because cli_scip.py
        line 1374 returns sym.name directly without calling _extract_display_name().

        ContextSymbol uses .name field (not .symbol), so the code must call
        _extract_display_name() on the .name fallback path.
        """
        # Create mock ContextSymbol with .name field containing full SCIP symbol
        # Note: We use spec=['name', 'line', 'relationship'] to ensure hasattr checks work correctly
        mock_symbol = Mock(spec=['name', 'line', 'relationship', 'column'])
        mock_symbol.name = (
            "scip-python python code-indexer abc123 `auth`/authenticate()."
        )
        mock_symbol.line = 45
        mock_symbol.column = 5
        mock_symbol.relationship = "definition"

        mock_file = Mock()
        mock_file.path = "src/auth.py"
        mock_file.relevance_score = 0.95
        mock_file.symbols = [mock_symbol]

        mock_context_result = Mock()
        mock_context_result.total_symbols = 1
        mock_context_result.total_files = 1
        mock_context_result.files = [mock_file]

        with patch(
            "code_indexer.scip.query.composites.get_smart_context"
        ) as mock_get_context:
            mock_get_context.return_value = mock_context_result

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_context

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_context, ["validate_token"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Find result line
                result_lines = [line for line in lines if "src/auth.py" in line]
                assert len(result_lines) >= 1

                # CRITICAL: Should contain CLEAN display name without verbose SCIP prefix
                result_line = result_lines[0]
                assert "auth/authenticate()." in result_line

                # Should NOT contain verbose SCIP prefix components
                assert "scip-python python code-indexer abc123" not in result_line
