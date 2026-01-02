"""Unit tests for SCIP CLI verification error reporting to stderr."""

from unittest.mock import Mock, patch
import click.testing


class TestSCIPVerificationStderr:
    """Test that SCIP verification errors are reported to stderr."""

    def _create_mock_scip_environment(self, tmp_path):
        """Create mock SCIP directory structure."""
        scip_dir = tmp_path / ".code-indexer" / "scip"
        scip_dir.mkdir(parents=True)

        scip_file = scip_dir / "test_project" / "index.scip"
        scip_file.parent.mkdir(parents=True)
        scip_file.touch()

        db_file = scip_file.with_suffix(scip_file.suffix + ".db")
        db_file.touch()

        return scip_dir, scip_file, db_file

    def _create_mock_generator_result(self, scip_file):
        """Create standard mock generator result for tests."""
        mock_indexer_result = Mock()
        mock_indexer_result.is_success.return_value = True
        mock_indexer_result.output_file = str(scip_file)
        mock_indexer_result.duration_seconds = 1.5
        mock_indexer_result.exit_code = 0
        mock_indexer_result.stdout = ""
        mock_indexer_result.stderr = ""

        mock_project = Mock()
        mock_project.relative_path = "test_project"
        mock_project.language = "python"
        mock_project.build_system = "poetry"

        mock_project_result = Mock()
        mock_project_result.project = mock_project
        mock_project_result.indexer_result = mock_indexer_result

        mock_result = Mock()
        mock_result.total_projects = 1
        mock_result.successful_projects = 1
        mock_result.failed_projects = 0
        mock_result.duration_seconds = 1.5
        mock_result.is_complete_success.return_value = True
        mock_result.is_partial_success.return_value = False
        mock_result.is_complete_failure.return_value = False
        mock_result.project_results = [mock_project_result]

        return mock_result

    @patch("code_indexer.scip.database.schema.DatabaseManager")
    @patch("code_indexer.scip.database.verify.SCIPDatabaseVerifier")
    @patch("code_indexer.scip.status.StatusTracker")
    @patch("code_indexer.scip.generator.SCIPGenerator")
    def test_verification_errors_go_to_stderr(
        self,
        mock_generator_cls,
        mock_tracker_cls,
        mock_verifier_cls,
        mock_db_manager_cls,
        tmp_path,
        monkeypatch,
    ):
        """Test that verification errors are written to stderr, not stdout.

        This ensures that subprocess.run() in golden_repo_manager.py can
        capture meaningful error messages in result.stderr when verification fails.
        """
        # Setup environment
        scip_dir, scip_file, db_file = self._create_mock_scip_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Setup mocks
        mock_result = self._create_mock_generator_result(scip_file)
        mock_generator = Mock()
        mock_generator.generate.return_value = mock_result
        mock_generator.scip_dir = scip_dir
        mock_generator_cls.return_value = mock_generator

        mock_tracker = Mock()
        mock_tracker_cls.return_value = mock_tracker

        # Mock verification to fail with specific errors
        mock_verify_result = Mock()
        mock_verify_result.passed = False
        mock_verify_result.total_errors = 3
        mock_verify_result.errors = [
            "Symbol count mismatch: expected 100, got 95",
            "Occurrence count mismatch: expected 500, got 490",
            "Document path mismatch: src/main.py missing",
        ]
        mock_verifier = Mock()
        mock_verifier.verify.return_value = mock_verify_result
        mock_verifier_cls.return_value = mock_verifier

        # Invoke the command
        from code_indexer.cli_scip import scip_generate

        runner = click.testing.CliRunner(mix_stderr=False)
        result = runner.invoke(scip_generate, [])

        # Assertions
        assert (
            result.exit_code == 1
        ), "Should exit with error code when verification fails"

        # CRITICAL: Verification error messages must be in stderr
        assert result.stderr, "stderr should not be empty when verification fails"
        assert (
            "Verification FAILED" in result.stderr
            or "verification errors" in result.stderr
        ), f"Expected verification error in stderr, got: {result.stderr}"
        assert (
            "Symbol count mismatch" in result.stderr
        ), f"Expected specific error in stderr, got: {result.stderr}"

        # Success messages should stay in stdout
        assert (
            "Successfully generated SCIP" in result.stdout
        ), "Generation success message should be in stdout"
