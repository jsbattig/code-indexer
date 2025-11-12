"""Centralized exception logger for CIDX.

Provides global exception logging with full debugging context including:
- Timestamp and process ID-based log files
- Complete stack traces
- Thread information
- Command context (for git operations)
- Mode-specific log file paths (CLI/Daemon vs Server)
"""

import json
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class ExceptionLogger:
    """Centralized exception logging facility.

    Logs all exceptions with full context to timestamped log files.
    Supports CLI, Daemon, and Server modes with appropriate log file locations.
    """

    _instance: Optional["ExceptionLogger"] = None
    log_file_path: Optional[Path] = None

    def __init__(self, log_file_path: Path):
        """Initialize exception logger with specific log file path.

        Args:
            log_file_path: Path to the log file for writing exceptions
        """
        self.log_file_path = log_file_path

    @classmethod
    def initialize(cls, project_root: Path, mode: str = "cli") -> "ExceptionLogger":
        """Initialize the global exception logger (idempotent singleton).

        Creates log file with timestamp and PID in the filename for uniqueness.

        WARNING: This is a singleton. If already initialized, returns the existing
        instance rather than creating a new one. Tests should manually reset
        cls._instance = None if they need fresh instances.

        Args:
            project_root: Root directory of the project
                         Note: Ignored in server mode (always uses ~/.cidx-server/logs)
            mode: Operating mode - "cli", "daemon", or "server"

        Returns:
            Initialized ExceptionLogger instance (singleton)
        """
        # If already initialized, return existing instance (idempotent)
        if cls._instance is not None:
            return cls._instance

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pid = os.getpid()

        if mode == "server":
            # Server mode: ~/.cidx-server/logs/
            log_dir = Path.home() / ".cidx-server" / "logs"
        else:
            # CLI/Daemon mode: <project>/.code-indexer/
            log_dir = project_root / ".code-indexer"

        # Create log directory if it doesn't exist
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create log file path with timestamp and PID
        log_file_path = log_dir / f"error_{timestamp}_{pid}.log"

        # Create the instance
        instance = cls(log_file_path)

        # Store as singleton
        cls._instance = instance

        # Create the log file (touch it to ensure it exists)
        log_file_path.touch()

        return instance

    @classmethod
    def get_instance(cls) -> Optional["ExceptionLogger"]:
        """Get the current exception logger instance.

        Returns:
            Current ExceptionLogger instance or None if not initialized
        """
        return cls._instance

    def log_exception(
        self,
        exception: Exception,
        thread_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an exception with full context.

        Args:
            exception: The exception to log
            thread_name: Name of the thread where exception occurred (optional)
            context: Additional context data to include in log (optional)
        """
        if not self.log_file_path:
            return  # Logger not initialized

        timestamp = datetime.now().isoformat()
        thread_info = thread_name or threading.current_thread().name

        log_entry = {
            "timestamp": timestamp,
            "thread": thread_info,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "stack_trace": traceback.format_exc(),
            "context": context or {},
        }

        # Write to log file (append mode)
        with open(self.log_file_path, "a") as f:
            f.write(json.dumps(log_entry, indent=2))
            f.write("\n---\n")

    def install_thread_exception_hook(self) -> None:
        """Install global thread exception handler.

        Sets up threading.excepthook to capture uncaught exceptions in threads.
        """

        def global_thread_exception_handler(args):
            """Handle uncaught thread exceptions."""
            self.log_exception(
                exception=args.exc_value,
                thread_name=args.thread.name,
                context={
                    "exc_type": args.exc_type.__name__,
                    "thread_identifier": args.thread.ident,
                },
            )

        # Install the hook globally
        threading.excepthook = global_thread_exception_handler
