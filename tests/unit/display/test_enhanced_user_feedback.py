"""Enhanced User Feedback Tests for Feature 3: Index Configuration Fixes Epic.

Tests for clear, helpful messaging for index operations and thread configuration
without confusion or duplicates.

Requirements:
- Clear index operation messaging without duplicates
- Configuration source transparency in thread count display
- Helpful error messages for invalid configurations
- Professional messaging that accurately reflects system behavior
"""

# Test modules will be implemented when we enhance the feedback system


class TestEnhancedIndexOperationMessaging:
    """Tests for clear index operation messaging without duplicates."""

    def test_clear_operation_messaging_no_duplicates(self):
        """PASSING TEST: Clear index operation shows single, clear message.

        Requirements:
        - Single message for clear operation start
        - No duplicate "clearing collection" messages
        - Professional language that accurately describes the operation
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationType,
            OperationContext,
        )

        # Test the enhanced message generator directly
        generator = EnhancedMessageGenerator()
        context = OperationContext(
            operation_type=OperationType.CLEAR,
            collection_name="test_collection",
            documents_before_clear=100,
        )

        # Get operation start message
        start_message = generator.get_operation_start_message(context)

        # Should have clear start message
        assert "🧹" in start_message, "Should use cleaning emoji for clear operation"
        assert "reindex" in start_message.lower(), "Should mention reindex"
        assert "clear" in start_message.lower(), "Should mention clearing"

        # Test collection operation message (should prevent duplicates)
        first_collection_msg = generator.get_collection_operation_message(context)
        second_collection_msg = generator.get_collection_operation_message(
            context
        )  # Should be None

        # Should have exactly one collection message
        assert (
            first_collection_msg is not None
        ), "Should have collection operation message"
        assert (
            second_collection_msg is None
        ), "Should prevent duplicate collection messages"
        assert (
            "🗑️" in first_collection_msg
        ), "Should use trash emoji for collection clearing"
        assert "100" in first_collection_msg, "Should show document count"

    def test_incremental_operation_messaging_clarity(self):
        """PASSING TEST: Incremental indexing shows clear progress messaging.

        Requirements:
        - Clear distinction between incremental and full indexing
        - Resume messaging when applicable
        - No confusing duplicates or technical jargon
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationType,
            OperationContext,
        )

        generator = EnhancedMessageGenerator()

        # Test resume operation message
        resume_context = OperationContext(
            operation_type=OperationType.RESUME,
            collection_name="test_collection",
            files_processed=50,
        )
        resume_message = generator.get_operation_start_message(resume_context)

        # Should have clear resume messaging
        assert "🔄" in resume_message, "Should use sync emoji for resume"
        assert "resum" in resume_message.lower(), "Should mention resuming"
        assert "incremental" in resume_message.lower(), "Should mention incremental"
        assert "50" in resume_message, "Should show files already processed"

        # Test fresh incremental operation message
        incremental_context = OperationContext(
            operation_type=OperationType.INCREMENTAL, collection_name="test_collection"
        )
        incremental_message = generator.get_operation_start_message(incremental_context)

        # Should have clear incremental messaging
        assert "🆕" in incremental_message, "Should use new emoji for fresh indexing"
        assert "fresh" in incremental_message.lower(), "Should mention fresh indexing"
        assert (
            "no previous index" in incremental_message.lower()
        ), "Should explain no previous index"

    def test_reconcile_operation_messaging_clarity(self):
        """PASSING TEST: Reconcile operation shows distinct, clear messaging.

        Requirements:
        - Clear explanation of reconcile vs. other operations
        - No technical jargon that confuses users
        - Single, professional message describing the operation
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationType,
            OperationContext,
        )

        generator = EnhancedMessageGenerator()

        # Test reconcile operation message
        reconcile_context = OperationContext(
            operation_type=OperationType.RECONCILE, collection_name="test_collection"
        )
        reconcile_message = generator.get_operation_start_message(reconcile_context)

        # Should have clear reconcile messaging
        assert "🔄" in reconcile_message, "Should use sync emoji for reconcile"
        assert "reconcil" in reconcile_message.lower(), "Should mention reconciliation"
        assert "sync" in reconcile_message.lower(), "Should mention syncing"
        assert "disk files" in reconcile_message.lower(), "Should mention disk files"
        assert "database" in reconcile_message.lower(), "Should mention database"

    def test_no_duplicate_collection_messages(self):
        """PASSING TEST: Collection operations don't show duplicate messages.

        Requirements:
        - Only one message per collection operation
        - No repeated "clearing collection" or "creating collection" messages
        - Messages should be consolidated and clear
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationType,
            OperationContext,
        )

        # Test duplicate prevention directly
        generator = EnhancedMessageGenerator()
        context = OperationContext(
            operation_type=OperationType.CLEAR,
            collection_name="test_collection",
            documents_before_clear=50,
        )

        # First call should return message
        first_message = generator.get_collection_operation_message(context)

        # Second call should return None (duplicate prevention)
        second_message = generator.get_collection_operation_message(context)

        # Third call should also return None
        third_message = generator.get_collection_operation_message(context)

        # Verify duplicate prevention
        assert first_message is not None, "Should provide first collection message"
        assert second_message is None, "Should prevent duplicate collection message"
        assert third_message is None, "Should continue preventing duplicates"

        # Verify message content
        assert "🗑️" in first_message, "Should use trash emoji"
        assert "clear" in first_message.lower(), "Should mention clearing"
        assert "50" in first_message, "Should show document count"


class TestConfigurationSourceTransparency:
    """Tests for configuration source transparency in thread count display."""

    def test_auto_detected_thread_count_display(self):
        """PASSING TEST: Auto-detected thread count shows clear source indication.

        Requirements:
        - Clear indication that thread count was auto-detected
        - Show which provider/system determined the count
        - Professional, informative messaging
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationContext,
            OperationType,
        )

        generator = EnhancedMessageGenerator()

        # Test auto-detected thread count display
        context = OperationContext(
            operation_type=OperationType.CLEAR,
            collection_name="test_collection",
            thread_count=8,
            thread_count_source="auto_detected",
            provider_name="ollama",
        )

        display_message = generator.get_thread_count_message(context)

        # Should clearly indicate auto-detection
        assert (
            "auto-detected" in display_message
        ), "Should clearly indicate auto-detection"
        assert (
            "ollama" in display_message
        ), "Should show which provider was used for detection"
        assert "🧵" in display_message, "Should use thread emoji"
        assert "8" in display_message, "Should show thread count"

    def test_user_specified_thread_count_display(self):
        """PASSING TEST: User-specified thread count shows clear source indication.

        Requirements:
        - Clear indication that user specified the thread count
        - Distinguish from auto-detected values
        - Show the actual user-provided value
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationContext,
            OperationType,
        )

        generator = EnhancedMessageGenerator()

        # Test user-specified thread count display
        context = OperationContext(
            operation_type=OperationType.CLEAR,
            collection_name="test_collection",
            thread_count=16,
            thread_count_source="user_specified",
            provider_name="ollama",
        )

        display_message = generator.get_thread_count_message(context)

        # Should clearly indicate user specification
        assert (
            "user specified" in display_message
        ), "Should clearly indicate user specification"
        assert "16" in display_message, "Should show the user-provided value"
        assert "🧵" in display_message, "Should use thread emoji"

    def test_configuration_override_transparency(self):
        """PASSING TEST: Configuration overrides are clearly communicated.

        Requirements:
        - When config file overrides defaults, show this clearly
        - Indicate the source of configuration values
        - Help users understand where values come from
        """
        from code_indexer.utils.enhanced_messaging import (
            EnhancedMessageGenerator,
            OperationContext,
            OperationType,
        )

        generator = EnhancedMessageGenerator()

        # Test config file override display
        context = OperationContext(
            operation_type=OperationType.CLEAR,
            collection_name="test_collection",
            thread_count=12,
            thread_count_source="config_file",
            provider_name="ollama",
        )

        display_message = generator.get_thread_count_message(context)

        # Should indicate config file source
        assert "config file" in display_message, "Should indicate config file source"
        assert "12" in display_message, "Should show configured value"
        assert "🧵" in display_message, "Should use thread emoji"


class TestHelpfulErrorMessages:
    """Tests for helpful error messages for invalid configurations."""

    def test_invalid_thread_count_error_message(self):
        """PASSING TEST: Invalid thread count shows helpful error message.

        Requirements:
        - Clear explanation of what went wrong
        - Suggest valid range or values
        - Professional, non-technical language
        """
        from code_indexer.utils.enhanced_messaging import (
            get_invalid_thread_count_message,
        )

        # Test invalid thread count error message
        invalid_thread_count = -1
        error_message = get_invalid_thread_count_message(invalid_thread_count)

        # Should provide helpful error message
        assert "❌" in error_message, "Should use error emoji"
        assert (
            "Invalid thread count" in error_message
        ), "Should clearly identify the problem"
        assert (
            str(invalid_thread_count) in error_message
        ), "Should show the invalid value provided"
        assert "must be at least 1" in error_message, "Should explain minimum value"
        assert "positive integer" in error_message, "Should suggest valid input type"

    def test_missing_service_error_message(self):
        """PASSING TEST: Missing service shows actionable error message.

        Requirements:
        - Clear explanation of what service is missing
        - Actionable suggestion (run 'start' command)
        - Professional, helpful tone
        """
        from code_indexer.utils.enhanced_messaging import (
            get_service_unavailable_message,
        )

        # Test service unavailable error message
        service_name = "Qdrant"
        error_message = get_service_unavailable_message(service_name, "cidx start")

        # Should provide actionable error message
        assert service_name in error_message, "Should name the specific service"
        assert "cidx start" in error_message, "Should suggest the start command"
        assert "❌" in error_message, "Should use error emoji"
        assert "not available" in error_message, "Should explain the problem"
        assert (
            "start required services" in error_message
        ), "Should explain what the command does"

    def test_configuration_validation_error_messages(self):
        """PASSING TEST: Configuration validation shows helpful error messages.

        Requirements:
        - Clear explanation of configuration problems
        - Suggest how to fix the issue
        - Reference specific config fields
        """
        from code_indexer.utils.enhanced_messaging import (
            get_configuration_error_message,
        )

        # Test configuration error messages
        config_errors = [
            {
                "field": "codebase_dir",
                "error": "Path does not exist: /invalid/path",
                "suggestion": "Ensure the codebase directory exists and is accessible",
            },
            {
                "field": "qdrant.host",
                "error": "Invalid host format",
                "suggestion": "Use a valid hostname or IP address",
            },
        ]

        for error_data in config_errors:
            # Get enhanced error message
            message = get_configuration_error_message(
                error_data["field"], error_data["error"], error_data["suggestion"]
            )

            # Should provide helpful error message
            assert "❌" in message, "Should use error emoji"
            assert "Configuration error" in message, "Should identify as config error"
            assert error_data["field"] in message, "Should reference specific field"
            assert error_data["error"] in message, "Should explain the problem"
            assert (
                error_data["suggestion"] in message
            ), "Should provide helpful suggestion"

    def test_conflicting_flags_error_message(self):
        """PASSING TEST: Conflicting flags show clear, helpful error message.

        Requirements:
        - Explain which flags conflict and why
        - Suggest valid combinations
        - Professional, educational tone
        """
        from code_indexer.utils.enhanced_messaging import get_conflicting_flags_message

        # Test conflicting flags error message
        error_message = get_conflicting_flags_message("--clear", "--reconcile")

        # Should provide helpful error message
        assert "❌" in error_message, "Should use error emoji"
        assert "--clear" in error_message, "Should mention clear flag"
        assert "--reconcile" in error_message, "Should mention reconcile flag"
        assert "together" in error_message, "Should explain they can't be used together"
        assert "complete reindex" in error_message, "Should explain what --clear does"
        assert (
            "sync with existing data" in error_message
        ), "Should explain what --reconcile does"
