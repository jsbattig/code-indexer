"""Integration tests for ExceptionLogger in server mode.

Tests that ExceptionLogger is properly initialized when FastAPI app starts
and that exceptions are logged to ~/.cidx-server/logs/error_*.log files.
"""



class TestServerExceptionLoggerIntegration:
    """Test ExceptionLogger integration with server app."""

    def test_server_app_initializes_exception_logger(self, tmp_path):
        """Test that create_app() initializes ExceptionLogger for server mode."""
        from code_indexer.server.app import create_app
        from code_indexer.utils.exception_logger import ExceptionLogger

        # Reset singleton if it exists from previous tests
        ExceptionLogger._instance = None

        # Create FastAPI app (should initialize ExceptionLogger)
        app = create_app()

        # Verify ExceptionLogger was initialized
        assert (
            ExceptionLogger._instance is not None
        ), "ExceptionLogger should be initialized"

        # Verify log file path is in ~/.cidx-server/logs/ (server mode location)
        assert ExceptionLogger._instance.log_file_path is not None
        assert ".cidx-server" in str(
            ExceptionLogger._instance.log_file_path
        ), "Log file should be in .cidx-server/logs/ directory for server mode"
        assert "logs" in str(
            ExceptionLogger._instance.log_file_path
        ), "Log file should be in logs subdirectory for server mode"
