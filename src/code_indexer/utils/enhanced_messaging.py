"""Enhanced User Feedback Messaging for Index Operations.

Provides clear, professional, and non-duplicate messaging for all index operations
including clear, reconcile, incremental, and error scenarios.
"""

from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum


class OperationType(Enum):
    """Types of indexing operations."""

    CLEAR = "clear"
    RECONCILE = "reconcile"
    INCREMENTAL = "incremental"
    RESUME = "resume"
    CONFIGURATION_CHANGE = "configuration_change"


@dataclass
class OperationContext:
    """Context information for an indexing operation."""

    operation_type: OperationType
    collection_name: str
    documents_before_clear: int = 0
    files_processed: int = 0
    chunks_indexed: int = 0
    provider_name: str = ""
    thread_count: int = 0
    thread_count_source: str = ""


class EnhancedMessageGenerator:
    """Generates clear, professional messages for index operations."""

    def __init__(self):
        self._messages_sent = set()  # Prevent duplicates

    def get_operation_start_message(self, context: OperationContext) -> str:
        """Get single, clear start message for operation."""
        if context.operation_type == OperationType.CLEAR:
            return "🧹 Starting complete reindex - all existing data will be cleared"

        elif context.operation_type == OperationType.RECONCILE:
            return "🔄 Starting reconciliation - syncing disk files with database index"

        elif context.operation_type == OperationType.RESUME:
            return f"🔄 Resuming incremental indexing - {context.files_processed} files already processed"

        elif context.operation_type == OperationType.INCREMENTAL:
            return "🆕 Starting fresh indexing - no previous index found"

        elif context.operation_type == OperationType.CONFIGURATION_CHANGE:
            return "⚙️ Configuration changed - performing full reindex to ensure consistency"

        return "📂 Starting indexing operation"

    def get_collection_operation_message(
        self, context: OperationContext
    ) -> Optional[str]:
        """Get single, clear collection operation message (prevents duplicates)."""
        message_key = (
            f"collection_{context.operation_type.value}_{context.collection_name}"
        )

        if message_key in self._messages_sent:
            return None  # Already sent this message

        self._messages_sent.add(message_key)

        if context.operation_type == OperationType.CLEAR:
            if context.documents_before_clear > 0:
                return f"🗑️ Cleared collection '{context.collection_name}' ({context.documents_before_clear:,} documents removed)"
            else:
                return f"🗑️ Cleared collection '{context.collection_name}' (collection was empty)"

        return None

    def get_thread_count_message(self, context: OperationContext) -> str:
        """Get clear thread count message with source transparency."""
        thread_count = context.thread_count
        source = context.thread_count_source
        provider = context.provider_name

        if source == "user_specified":
            return f"🧵 Vector calculation threads: {thread_count} (user specified)"

        elif source == "config_file":
            return f"🧵 Vector calculation threads: {thread_count} (from config file)"

        elif source == "auto_detected":
            return f"🧵 Vector calculation threads: {thread_count} (auto-detected for {provider})"

        else:
            # Fallback for unknown source
            return f"🧵 Vector calculation threads: {thread_count}"

    def get_progress_start_message(
        self, total_files: int, operation_type: OperationType
    ) -> str:
        """Get clear progress start message."""
        if operation_type == OperationType.CLEAR:
            return f"🔄 Processing {total_files:,} files for complete reindex"

        elif operation_type == OperationType.RECONCILE:
            return f"🔄 Analyzing {total_files:,} files for reconciliation"

        elif operation_type == OperationType.RESUME:
            return f"🔄 Continuing with {total_files:,} remaining files"

        else:
            return f"🔄 Processing {total_files:,} files for indexing"

    def reset_message_tracking(self):
        """Reset message tracking for new operation."""
        self._messages_sent.clear()


class EnhancedProgressCallback:
    """Enhanced progress callback that provides clear, non-duplicate messaging."""

    def __init__(self, original_callback: Callable, context: OperationContext):
        """
        Initialize enhanced progress callback.

        Args:
            original_callback: Original progress callback function
            context: Operation context for message generation
        """
        self.original_callback = original_callback
        self.context = context
        self.message_generator = EnhancedMessageGenerator()
        self._operation_started = False

    def __call__(self, current: int, total: int, file_path: Path, **kwargs):
        """Enhanced progress callback with clear messaging."""
        info = kwargs.get("info")

        # Send operation start message once
        if not self._operation_started and total > 0:
            start_message = self.message_generator.get_operation_start_message(
                self.context
            )
            if start_message:
                self.original_callback(0, 0, Path(""), info=start_message)

            self._operation_started = True

        # Handle collection operation messages (prevents duplicates)
        if info and "collection" in info.lower() and "clear" in info.lower():
            collection_message = (
                self.message_generator.get_collection_operation_message(self.context)
            )
            if collection_message:
                self.original_callback(0, 0, Path(""), info=collection_message)
            return  # Don't send the original duplicate message

        # Pass through other messages as normal
        self.original_callback(current, total, file_path, **kwargs)


def create_enhanced_callback(
    original_callback: Callable,
    operation_type: OperationType,
    collection_name: str = "",
    documents_before_clear: int = 0,
    provider_name: str = "",
    thread_count: int = 0,
    thread_count_source: str = "",
) -> EnhancedProgressCallback:
    """
    Create an enhanced progress callback with clear messaging.

    Args:
        original_callback: Original progress callback function
        operation_type: Type of operation being performed
        collection_name: Name of collection being operated on
        documents_before_clear: Number of documents before clearing (for clear operations)
        provider_name: Name of embedding provider
        thread_count: Number of threads being used
        thread_count_source: Source of thread count (user_specified, config_file, auto_detected)

    Returns:
        Enhanced progress callback with clear, non-duplicate messaging
    """
    context = OperationContext(
        operation_type=operation_type,
        collection_name=collection_name,
        documents_before_clear=documents_before_clear,
        provider_name=provider_name,
        thread_count=thread_count,
        thread_count_source=thread_count_source,
    )

    return EnhancedProgressCallback(original_callback, context)


# Convenience functions for common error messages
def get_invalid_thread_count_message(invalid_count: int) -> str:
    """Get helpful error message for invalid thread count."""
    return f"❌ Invalid thread count: {invalid_count}. Thread count must be at least 1. Use a positive integer value."


def get_service_unavailable_message(
    service_name: str, command_suggestion: str = "cidx start"
) -> str:
    """Get helpful error message for unavailable service."""
    return f"❌ {service_name} service not available. Run '{command_suggestion}' to start required services."


def get_conflicting_flags_message(flag1: str, flag2: str) -> str:
    """Get helpful error message for conflicting flags."""
    explanations = {
        "--clear": "complete reindex (removes all existing data)",
        "--reconcile": "sync with existing data (preserves valid entries)",
    }

    explanation1 = explanations.get(flag1, "see documentation")
    explanation2 = explanations.get(flag2, "see documentation")

    return f"❌ Cannot use {flag1} and {flag2} together. Use {flag1} for {explanation1} or {flag2} for {explanation2}."


def get_configuration_error_message(field: str, error: str, suggestion: str) -> str:
    """Get helpful error message for configuration problems."""
    return f"❌ Configuration error in '{field}': {error}. {suggestion}"
