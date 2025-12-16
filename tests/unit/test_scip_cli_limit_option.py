"""Unit tests for --limit option on all SCIP CLI query commands."""

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


class TestDefinitionLimit:
    """Test --limit option for 'cidx scip definition' command."""

    def test_definition_with_limit_zero_returns_all_results(self, mock_scip_environment):
        """Test that definition --limit 0 returns all results (unlimited)."""
        # Create 5 mock results
        mock_results = [
            Mock(
                symbol=f"scip-python python code-indexer abc123 `auth`/authenticate{i}().",
                file_path=f"src/auth{i}.py",
                line=45 + i,
                column=10,
            )
            for i in range(5)
        ]

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.find_definition.return_value = mock_results
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_definition

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_definition, ["authenticate", "--limit", "0"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Count result lines (should be all 5)
                result_lines = [line for line in lines if "auth" in line and ".py:" in line]
                assert len(result_lines) == 5

    def test_definition_with_limit_five_returns_max_five_results(self, mock_scip_environment):
        """Test that definition --limit 5 returns at most 5 results."""
        # Create 10 mock results
        mock_results = [
            Mock(
                symbol=f"scip-python python code-indexer abc123 `auth`/authenticate{i}().",
                file_path=f"src/auth{i}.py",
                line=45 + i,
                column=10,
            )
            for i in range(10)
        ]

        with patch("code_indexer.scip.query.SCIPQueryEngine") as mock_engine_cls:
            mock_engine = Mock()
            mock_engine.find_definition.return_value = mock_results
            mock_engine_cls.return_value = mock_engine

            with patch("code_indexer.scip.status.StatusTracker") as mock_tracker_cls:
                mock_tracker = Mock()
                mock_status = Mock()
                mock_status.projects = {"test": "project"}
                mock_tracker.load.return_value = mock_status
                mock_tracker_cls.return_value = mock_tracker

                from code_indexer.cli_scip import scip_definition

                runner = click.testing.CliRunner()
                result = runner.invoke(scip_definition, ["authenticate", "--limit", "5"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Count result lines (should be max 5)
                result_lines = [line for line in lines if "auth" in line and ".py:" in line]
                assert len(result_lines) <= 5

    def test_definition_default_limit_is_zero(self, mock_scip_environment):
        """Test that definition command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_definition

        # Check the option definition
        limit_option = [p for p in scip_definition.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"


class TestReferencesLimit:
    """Test --limit option for 'cidx scip references' command."""

    def test_references_default_limit_is_zero(self, mock_scip_environment):
        """Test that references command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_references

        # Check the option definition
        limit_option = [p for p in scip_references.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"

    def test_references_with_limit_zero_returns_all_results(self, mock_scip_environment):
        """Test that references --limit 0 returns all results (unlimited)."""
        # Create 8 mock results
        mock_results = [
            Mock(
                symbol="scip-python python code-indexer abc123 `auth`/authenticate().",
                file_path=f"src/file{i}.py",
                line=45 + i,
                column=10,
            )
            for i in range(8)
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
                result = runner.invoke(scip_references, ["authenticate", "--limit", "0"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Count result lines (should be all 8)
                result_lines = [line for line in lines if "file" in line and ".py:" in line]
                assert len(result_lines) == 8


class TestDependenciesLimit:
    """Test --limit option for 'cidx scip dependencies' command."""

    def test_dependencies_with_limit_zero_returns_all_results(self, mock_scip_environment):
        """Test that dependencies --limit 0 returns all results (unlimited)."""
        # Create 6 mock results
        mock_results = [
            Mock(
                symbol=f"scip-python python code-indexer abc123 `db`/UserRepo{i}#save().",
                file_path=f"src/db/repo{i}.py",
                line=67 + i,
                relationship="reference",
            )
            for i in range(6)
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
                result = runner.invoke(scip_dependencies, ["UserService", "--limit", "0"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Count result lines (should be all 6)
                result_lines = [line for line in lines if "repo" in line and ".py:" in line]
                assert len(result_lines) == 6

    def test_dependencies_default_limit_is_zero(self, mock_scip_environment):
        """Test that dependencies command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_dependencies

        # Check the option definition
        limit_option = [p for p in scip_dependencies.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"


class TestDependentsLimit:
    """Test --limit option for 'cidx scip dependents' command."""

    def test_dependents_with_limit_zero_returns_all_results(self, mock_scip_environment):
        """Test that dependents --limit 0 returns all results (unlimited)."""
        # Create 7 mock results
        mock_results = [
            Mock(
                symbol=f"scip-python python code-indexer abc123 `services`/Service{i}#create().",
                file_path=f"src/services/service{i}.py",
                line=89 + i,
                relationship="call",
            )
            for i in range(7)
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
                result = runner.invoke(scip_dependents, ["UserRepo", "--limit", "0"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Count result lines (should be all 7)
                result_lines = [line for line in lines if "service" in line and ".py:" in line]
                assert len(result_lines) == 7

    def test_dependents_default_limit_is_zero(self, mock_scip_environment):
        """Test that dependents command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_dependents

        # Check the option definition
        limit_option = [p for p in scip_dependents.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"


class TestImpactLimit:
    """Test --limit option for 'cidx scip impact' command."""

    def test_impact_with_limit_zero_returns_all_results(self, mock_scip_environment):
        """Test that impact --limit 0 returns all results (unlimited)."""
        # Create 9 mock results
        mock_results = [
            Mock(
                symbol=f"scip-python python code-indexer abc123 `auth`/auth{i}().",
                file_path=f"src/auth{i}.py",
                line=45 + i,
                depth=1,
            )
            for i in range(9)
        ]

        mock_impact_result = Mock()
        mock_impact_result.total_affected = 9
        mock_impact_result.affected_files = [Mock(path=f"src/auth{i}.py") for i in range(9)]
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
                result = runner.invoke(scip_impact, ["validate_token", "--limit", "0"])

                assert result.exit_code == 0
                lines = result.output.strip().split("\n")

                # Count result lines (should be all 9)
                result_lines = [line for line in lines if "auth" in line and ".py:" in line]
                assert len(result_lines) == 9

    def test_impact_default_limit_is_zero(self, mock_scip_environment):
        """Test that impact command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_impact

        # Check the option definition
        limit_option = [p for p in scip_impact.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"


class TestCallchainLimit:
    """Test --limit option for 'cidx scip callchain' command."""

    def test_callchain_default_limit_is_zero(self, mock_scip_environment):
        """Test that callchain command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_callchain

        # Check the option definition
        limit_option = [p for p in scip_callchain.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"


class TestContextLimit:
    """Test --limit option for 'cidx scip context' command."""

    def test_context_default_limit_is_zero(self, mock_scip_environment):
        """Test that context command has default limit=0 (unlimited)."""
        from code_indexer.cli_scip import scip_context

        # Check the option definition
        limit_option = [p for p in scip_context.params if p.name == "limit"]
        assert len(limit_option) == 1, "Should have --limit option"
        assert limit_option[0].default == 0, "Default should be 0 (unlimited)"
