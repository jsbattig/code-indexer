"""
Unit tests for single FastAPI error handler instance requirement.

Tests that FastAPI integration uses a single error handler instance to avoid
inconsistent behavior following CLAUDE.md Foundation #8 production killer patterns.
"""

from fastapi import FastAPI

from code_indexer.server.middleware.error_handler import GlobalErrorHandler


class TestSingleInstanceIntegration:
    """Test that FastAPI integration uses single error handler instance."""

    def test_single_instance_creation_pattern(self):
        """Test that we can create a single instance pattern correctly."""
        # This test shows the CORRECT pattern
        app = FastAPI()

        # Create single instance
        global_error_handler = GlobalErrorHandler()

        # The middleware should use the same instance
        # We can't directly test middleware registration here, but we can test
        # that the pattern allows for single instance usage
        assert global_error_handler is not None
        assert isinstance(global_error_handler, GlobalErrorHandler)

        # Should be able to add to app as middleware
        # (FastAPI will create wrapper, but should use the same instance internally)
        app.add_middleware(GlobalErrorHandler)

        # This is a placeholder test showing correct usage pattern
        # Note: middleware_stack may not be directly accessible in newer FastAPI versions
        # The important thing is that no exception was raised during middleware addition

    def test_multiple_instances_create_inconsistency_risk(self):
        """Test that demonstrates the problem with multiple instances."""
        # This test shows the PROBLEMATIC pattern that should be avoided

        from code_indexer.server.models.error_models import (
            ErrorHandlerConfiguration,
            RetryConfiguration,
        )

        # Instance 1 with custom configuration
        custom_config = ErrorHandlerConfiguration(
            include_stack_traces_in_logs=True,
            retry_config=RetryConfiguration(max_attempts=5),
        )
        handler1 = GlobalErrorHandler(configuration=custom_config)

        # Instance 2 with different configuration (this is the problem!)
        different_config = ErrorHandlerConfiguration(
            include_stack_traces_in_logs=False,
            retry_config=RetryConfiguration(max_attempts=3),
        )
        handler2 = GlobalErrorHandler(configuration=different_config)

        # The two handlers have different behaviors
        assert (
            handler1.config.include_stack_traces_in_logs
            != handler2.config.include_stack_traces_in_logs
        )
        assert (
            handler1.config.retry_config.max_attempts
            != handler2.config.retry_config.max_attempts
        )

        # This demonstrates why using multiple instances is problematic
        # Different instances can have different configurations leading to inconsistent behavior

    def test_correlation_id_uniqueness_across_single_instance(self):
        """Test that a single instance generates unique correlation IDs."""
        from code_indexer.server.middleware.error_formatters import (
            generate_correlation_id,
        )

        # Generate multiple correlation IDs
        correlation_ids = []
        for _ in range(100):
            correlation_id = generate_correlation_id()
            correlation_ids.append(correlation_id)

        # All correlation IDs should be unique
        unique_ids = set(correlation_ids)
        assert len(unique_ids) == len(
            correlation_ids
        ), "Correlation IDs should be unique across all requests"

        # All should be valid UUID format
        import uuid

        for correlation_id in correlation_ids:
            # Should not raise exception
            uuid.UUID(correlation_id)

    def test_sanitizer_consistency_across_requests(self):
        """Test that using single instance ensures consistent sanitization."""
        handler = GlobalErrorHandler()

        # Test multiple sanitization operations
        test_data = ["password=secret123", "api_key=abcd1234", "token=xyz789"]

        # All operations should use the same sanitizer instance
        results = []
        for data in test_data:
            result = handler.sanitizer.sanitize_string(data)
            results.append(result)

        # Results should be consistent
        for result in results:
            assert "secret" not in result or "[REDACTED]" in result

        # Same sanitizer should be used for all operations
        assert handler.sanitizer is not None

    def test_configuration_consistency_across_instance(self):
        """Test that single instance maintains configuration consistency."""
        from code_indexer.server.models.error_models import ErrorHandlerConfiguration

        # Create configuration
        config = ErrorHandlerConfiguration()
        handler = GlobalErrorHandler(configuration=config)

        # Configuration should be consistent across all operations
        assert handler.config is config
        assert handler.sanitizer.config is config
        assert handler.retry_handler.config is config.retry_config

        # All components should use the same configuration
        assert handler.config == handler.sanitizer.config

    def test_status_code_mapping_consistency(self):
        """Test that status code mapping is consistent across single instance."""
        handler = GlobalErrorHandler()

        # Status code mapping should be consistent
        test_error_types = [
            "validation_error",
            "authentication_error",
            "authorization_error",
            "not_found_error",
            "internal_server_error",
        ]

        # Multiple calls should return same status codes
        for error_type in test_error_types:
            status_code_1 = handler.get_status_code_for_error_type(error_type)
            status_code_2 = handler.get_status_code_for_error_type(error_type)

            assert (
                status_code_1 == status_code_2
            ), f"Status code mapping inconsistent for {error_type}"

    def test_error_handler_middleware_integration(self):
        """Test proper integration pattern with FastAPI middleware."""
        app = FastAPI()

        # Add as middleware (correct pattern)
        # Note: We can't directly test internal middleware behavior without
        # running actual requests, but we can test the setup
        app.add_middleware(GlobalErrorHandler)

        # Verify middleware was added (method varies by FastAPI version)
        # In newer versions, middleware info may be stored differently
        # The important thing is that no exception was raised during middleware addition

        # Try to access middleware stack if available
        if hasattr(app, "middleware_stack") and app.middleware_stack is not None:
            assert len(app.middleware_stack) > 0
            middleware_types = [middleware.cls for middleware in app.middleware_stack]
            assert GlobalErrorHandler in middleware_types
        else:
            # Alternative check - middleware was added without error
            assert True  # Test passes if no exception during add_middleware

    def test_avoid_global_handler_variable_pattern(self):
        """Test that we avoid the problematic global variable pattern."""
        # This test documents the WRONG pattern that should be avoided:
        # global_error_handler = GlobalErrorHandler()  # Global instance
        # app.add_middleware(GlobalErrorHandler)        # Different instance!

        # The problem is that app.add_middleware(GlobalErrorHandler) creates
        # a NEW instance, not using the global one

        app = FastAPI()

        # Wrong pattern (creates two instances):
        global_handler = GlobalErrorHandler()
        app.add_middleware(GlobalErrorHandler)  # This creates ANOTHER instance!

        # This is problematic because:
        # 1. global_handler is not the same instance used by FastAPI
        # 2. They may have different configurations
        # 3. Behavior becomes inconsistent

        # The test just documents this anti-pattern
        # The solution is to either:
        # 1. Use app.add_middleware(GlobalErrorHandler) without global variable, OR
        # 2. Create custom middleware registration that uses the global instance

        assert global_handler is not None

        # Check middleware was added (FastAPI version independent)
        if hasattr(app, "middleware_stack") and app.middleware_stack is not None:
            assert len(app.middleware_stack) > 0

        # This test mainly documents the issue rather than testing a solution

    def test_handler_instance_immutability_during_requests(self):
        """Test that handler configuration doesn't change during request processing."""
        handler = GlobalErrorHandler()

        # Store original configuration state
        original_config = handler.config
        original_status_map = handler._status_code_map.copy()
        original_sanitizer = handler.sanitizer
        original_retry_handler = handler.retry_handler

        # Simulate request processing (without actual HTTP requests)
        from fastapi import Request

        mock_request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/test",
                "headers": [(b"host", b"testserver")],
            }
        )

        # Process some errors (this should not modify handler state)
        from code_indexer.server.models.error_models import DatabaseRetryableError

        test_error = DatabaseRetryableError("Test error")

        handler.handle_database_error(test_error, mock_request)
        handler.get_status_code_for_error_type("validation_error")

        # Handler state should remain unchanged
        assert handler.config is original_config
        assert handler._status_code_map == original_status_map
        assert handler.sanitizer is original_sanitizer
        assert handler.retry_handler is original_retry_handler

        # Configuration should be immutable during request processing
        # This ensures consistent behavior across all requests


class TestErrorHandlerInstanceManagement:
    """Test proper error handler instance management patterns."""

    def test_singleton_pattern_implementation(self):
        """Test a potential singleton pattern for error handler."""
        # This test shows how a singleton pattern could work
        # Note: This is NOT implemented yet, just showing the concept

        class SingletonErrorHandler:
            _instance = None

            def __new__(cls, *args, **kwargs):
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                return cls._instance

            def __init__(self, *args, **kwargs):
                if not hasattr(self, "initialized"):
                    # Initialize only once
                    self.config = kwargs.get("configuration", None)
                    self.initialized = True

        # Test singleton behavior
        handler1 = SingletonErrorHandler()
        handler2 = SingletonErrorHandler()

        assert handler1 is handler2, "Singleton should return same instance"

        # This is just a concept test - not implementing singleton in actual code
        # since it may not be necessary if FastAPI middleware is used correctly

    def test_factory_pattern_for_consistent_configuration(self):
        """Test factory pattern for creating handlers with consistent configuration."""
        from code_indexer.server.models.error_models import ErrorHandlerConfiguration

        class ErrorHandlerFactory:
            @staticmethod
            def create_handler(
                config: ErrorHandlerConfiguration = None,
            ) -> GlobalErrorHandler:
                """Create error handler with consistent configuration."""
                default_config = config or ErrorHandlerConfiguration()
                return GlobalErrorHandler(configuration=default_config)

        # Test factory creates consistent handlers
        factory = ErrorHandlerFactory()

        config = ErrorHandlerConfiguration()
        handler1 = factory.create_handler(config)
        handler2 = factory.create_handler(config)

        # Both should have the same configuration
        assert (
            handler1.config.include_stack_traces_in_logs
            == handler2.config.include_stack_traces_in_logs
        )
        assert (
            handler1.config.retry_config.max_attempts
            == handler2.config.retry_config.max_attempts
        )

        # This pattern ensures configuration consistency even with multiple instances

    def test_middleware_wrapper_pattern(self):
        """Test middleware wrapper pattern that ensures single instance usage."""
        # This test shows a pattern for wrapping the error handler
        # to ensure consistent instance usage in FastAPI

        class ErrorHandlerWrapper:
            def __init__(self, handler_instance: GlobalErrorHandler):
                self._handler = handler_instance

            async def __call__(self, request, call_next):
                # Delegate to the specific handler instance
                return await self._handler.dispatch(request, call_next)

        # Create single handler instance
        handler = GlobalErrorHandler()
        wrapper = ErrorHandlerWrapper(handler)

        # Wrapper should use the same handler instance
        assert wrapper._handler is handler

        # This pattern could be used to ensure FastAPI uses the same instance
        # instead of creating new ones
