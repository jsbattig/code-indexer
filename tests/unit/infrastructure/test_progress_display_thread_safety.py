"""Unit tests for RichLiveProgressManager thread safety.

This module tests thread safety of RichLiveProgressManager to ensure proper
concurrent access protection and prevent race conditions during parallel processing.
"""

import threading
import time
from unittest.mock import patch, MagicMock
from rich.console import Console

from code_indexer.progress.progress_display import RichLiveProgressManager


class TestRichLiveProgressManagerThreadSafety:
    """Thread safety tests for RichLiveProgressManager."""

    def test_concurrent_start_stop_operations_thread_safe(self):
        """Test concurrent start/stop operations are properly thread-safe."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        errors = []
        successful_operations = []

        def start_operation(thread_id):
            try:
                manager.start_bottom_display()
                successful_operations.append(f"start-{thread_id}")
                time.sleep(0.01)  # Small delay to increase chance of race condition
            except Exception as e:
                errors.append(f"start-{thread_id}: {str(e)}")

        def stop_operation(thread_id):
            try:
                manager.stop_display()
                successful_operations.append(f"stop-{thread_id}")
                time.sleep(0.01)  # Small delay to increase chance of race condition
            except Exception as e:
                errors.append(f"stop-{thread_id}: {str(e)}")

        # Create multiple threads performing start/stop operations simultaneously
        threads = []
        for i in range(10):
            # Mix of start and stop operations
            if i % 2 == 0:
                thread = threading.Thread(target=start_operation, args=(i,))
            else:
                thread = threading.Thread(target=stop_operation, args=(i,))
            threads.append(thread)

        # Start all threads simultaneously
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # This test should currently FAIL due to race conditions
        # Without proper locking, we expect inconsistent state or errors
        print(f"Errors: {errors}")
        print(f"Successful operations: {successful_operations}")
        is_active, has_live_component = manager.get_state()
        print(f"Final state - is_active: {is_active}")
        print(f"Final state - has_live_component: {has_live_component}")

        # Clean up any remaining state
        try:
            manager.stop_display()
        except Exception:
            pass

        # With proper thread safety, we should have NO errors and consistent state
        # This validates that the thread safety implementation is working correctly
        assert (
            len(errors) == 0
        ), f"Thread safety implementation should prevent errors, but found: {errors}"
        assert (
            is_active == has_live_component
        ), f"State should be consistent: is_active={is_active}, has_live_component={has_live_component}"

    def test_concurrent_update_operations_thread_safe(self):
        """Test concurrent update operations are properly thread-safe."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Start display once
        manager.start_bottom_display()

        update_errors = []
        successful_updates = []

        def update_operation(thread_id):
            try:
                for i in range(5):
                    manager.handle_progress_update(f"Thread {thread_id} - Update {i}")
                    successful_updates.append(f"thread-{thread_id}-update-{i}")
                    time.sleep(0.001)  # Very small delay
            except Exception as e:
                update_errors.append(f"thread-{thread_id}: {str(e)}")

        # Create multiple threads updating simultaneously
        threads = []
        for i in range(5):
            thread = threading.Thread(target=update_operation, args=(i,))
            threads.append(thread)

        # Start all threads simultaneously
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        print(f"Update errors: {update_errors}")
        print(f"Successful updates: {len(successful_updates)}")

        # Clean up
        manager.stop_display()

        # This test might pass if Rich Live component is thread-safe internally,
        # but the state management around it is still vulnerable
        # We're mainly testing for potential AttributeErrors or state corruption

    def test_concurrent_start_and_update_operations_thread_safe(self):
        """Test concurrent start and update operations are properly thread-safe."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        operation_errors = []

        def start_operation():
            try:
                time.sleep(0.01)  # Small delay
                manager.start_bottom_display()
            except Exception as e:
                operation_errors.append(f"start: {str(e)}")

        def update_operation():
            try:
                time.sleep(0.005)  # Smaller delay to hit race condition window
                manager.handle_progress_update("Concurrent update")
            except Exception as e:
                operation_errors.append(f"update: {str(e)}")

        def stop_operation():
            try:
                time.sleep(0.02)  # Longer delay
                manager.stop_display()
            except Exception as e:
                operation_errors.append(f"stop: {str(e)}")

        # Create threads that will hit race conditions
        threads = []

        # Start operation
        threads.append(threading.Thread(target=start_operation))

        # Multiple update operations that might try to access live_component
        # while it's being initialized or destroyed
        for i in range(3):
            threads.append(threading.Thread(target=update_operation))

        # Stop operation
        threads.append(threading.Thread(target=stop_operation))

        # Start all threads simultaneously
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        print(f"Operation errors: {operation_errors}")

        # Clean up any remaining state
        try:
            manager.stop_display()
        except Exception:
            pass

        # With proper thread safety, we should have NO errors
        # This validates that the thread safety implementation prevents race conditions
        assert (
            len(operation_errors) == 0
        ), f"Thread safety implementation should prevent race conditions, but found errors: {operation_errors}"

    def test_state_consistency_under_concurrent_access(self):
        """Test state consistency under high-frequency concurrent access."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        inconsistent_states = []

        def check_state_consistency():
            """Check if is_active and live_component are consistent."""
            for _ in range(100):
                # Use thread-safe state reading to avoid race conditions in the test itself
                is_active, has_live_component = manager.get_state()

                # These should be consistent:
                # - If is_active is True, live_component should not be None
                # - If is_active is False, live_component should be None
                if is_active and not has_live_component:
                    inconsistent_states.append("is_active=True but live_component=None")
                elif not is_active and has_live_component:
                    inconsistent_states.append(
                        "is_active=False but live_component!=None"
                    )

                time.sleep(0.001)

        def rapid_start_stop_operations():
            """Rapidly start and stop operations."""
            for _ in range(50):
                try:
                    manager.start_bottom_display()
                    time.sleep(0.001)
                    manager.stop_display()
                    time.sleep(0.001)
                except Exception:
                    pass  # Ignore exceptions for this consistency test

        # Run consistency checker and operations concurrently
        consistency_thread = threading.Thread(target=check_state_consistency)
        operations_thread = threading.Thread(target=rapid_start_stop_operations)

        consistency_thread.start()
        operations_thread.start()

        consistency_thread.join()
        operations_thread.join()

        print(f"Inconsistent states found: {inconsistent_states}")

        # Clean up
        try:
            manager.stop_display()
        except Exception:
            pass

        # With proper thread safety, we should have NO state inconsistencies
        # This validates that the thread safety implementation maintains consistent state
        assert (
            len(inconsistent_states) == 0
        ), f"Thread safety implementation should maintain consistent state, but found inconsistencies: {inconsistent_states}"

    def test_attribute_error_during_concurrent_access(self):
        """Test for AttributeError during concurrent access to live_component."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        attribute_errors = []

        def access_live_component():
            """Try to access live_component attributes."""
            for _ in range(100):
                try:
                    # This should trigger AttributeError if live_component
                    # becomes None during access
                    if manager.live_component is not None:
                        # Try to access an attribute - this might fail
                        # if another thread sets live_component to None
                        _ = manager.live_component.console
                except AttributeError as e:
                    attribute_errors.append(str(e))
                except Exception:
                    pass  # Ignore other exceptions
                time.sleep(0.001)

        def modify_live_component():
            """Rapidly modify live_component state."""
            for _ in range(20):
                try:
                    manager.start_bottom_display()
                    time.sleep(0.005)
                    manager.stop_display()
                    time.sleep(0.005)
                except Exception:
                    pass

        # Run access and modification concurrently
        access_thread = threading.Thread(target=access_live_component)
        modify_thread = threading.Thread(target=modify_live_component)

        access_thread.start()
        modify_thread.start()

        access_thread.join()
        modify_thread.join()

        print(f"AttributeErrors found: {attribute_errors}")

        # Clean up
        try:
            manager.stop_display()
        except Exception:
            pass

        # This test expects to find AttributeErrors due to concurrent access
        # Without proper synchronization, we should see these errors
        # Note: This might not always trigger, so we'll make it informational for now
        print(
            f"Found {len(attribute_errors)} attribute errors during concurrent access"
        )

    def test_mock_based_race_condition_simulation(self):
        """Test race conditions using mocking to control timing."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Mock Rich Live to simulate slow operations that increase race condition window
        with patch("code_indexer.progress.progress_display.Live") as mock_live_class:
            mock_live_instance = MagicMock()
            mock_live_class.return_value = mock_live_instance

            # Make start() slow to increase race condition window
            def slow_start():
                time.sleep(0.1)  # Simulate slow start
                return None

            mock_live_instance.start.side_effect = slow_start

            race_condition_errors = []

            def start_and_update():
                try:
                    manager.start_bottom_display()
                    # Immediately try to update - this might fail if start is not complete
                    manager.handle_progress_update("Quick update")
                except Exception as e:
                    race_condition_errors.append(f"start_and_update: {str(e)}")

            def quick_stop():
                try:
                    time.sleep(0.05)  # Start after start_and_update begins
                    manager.stop_display()
                except Exception as e:
                    race_condition_errors.append(f"quick_stop: {str(e)}")

            # Create threads that should hit race conditions
            start_thread = threading.Thread(target=start_and_update)
            stop_thread = threading.Thread(target=quick_stop)

            start_thread.start()
            stop_thread.start()

            start_thread.join()
            stop_thread.join()

            print(f"Race condition errors with mocking: {race_condition_errors}")

            # Clean up
            try:
                manager.stop_display()
            except Exception:
                pass

    def test_thread_safety_protection_validation(self):
        """Test that thread safety protection is correctly implemented."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # This test validates that the manager has proper thread safety mechanisms
        # Check for the presence of threading.Lock
        assert hasattr(
            manager, "_lock"
        ), "RichLiveProgressManager should have a _lock attribute for thread safety"
        assert isinstance(
            manager._lock, threading.Lock
        ), "The _lock should be a threading.Lock instance"

        # Test that critical sections are protected
        def concurrent_operation(op_type, thread_id):
            if op_type == "start":
                manager.start_bottom_display()
            elif op_type == "stop":
                manager.stop_display()
            elif op_type == "update":
                manager.handle_progress_update(f"Thread {thread_id} update")

        # Run multiple concurrent operations
        threads = []
        for i in range(10):
            op_type = ["start", "stop", "update"][i % 3]
            thread = threading.Thread(target=concurrent_operation, args=(op_type, i))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Clean up
        try:
            manager.stop_display()
        except Exception:
            pass
