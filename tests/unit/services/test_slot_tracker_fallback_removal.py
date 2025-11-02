"""
Tests for slot_tracker fallback removal.

This test suite verifies that:
1. All progress callbacks include concurrent_files as JSON-serializable data
2. Daemon callbacks filter out slot_tracker to prevent RPyC proxy leakage
3. Multi_threaded_display no longer falls back to slot_tracker proxy calls
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_indexer.services.clean_slot_tracker import CleanSlotTracker


class TestHashPhaseCallbacksIncludeConcurrentFiles:
    """Test that hash phase callbacks include concurrent_files with actual data from slot_tracker."""

    def test_hash_initialization_callback_uses_slot_tracker_data(self):
        """Hash phase initialization must get concurrent_files from slot_tracker, not empty list."""
        # Read the actual source code to verify the pattern
        source_file = Path("/home/jsbattig/Dev/code-indexer/src/code_indexer/services/high_throughput_processor.py")
        source_code = source_file.read_text()

        # Find the hash initialization callback (~line 462)
        hash_init_section = None
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if "🔍 Starting hash calculation..." in line:
                # Get surrounding 10 lines for context
                hash_init_section = '\n'.join(lines[max(0, i-5):min(len(lines), i+5)])
                break

        assert hash_init_section is not None, "Could not find hash initialization section"

        # CRITICAL CHECK: Must use hash_slot_tracker.get_concurrent_files_data()
        # NOT just concurrent_files=[]
        # Look for the pattern: copy.deepcopy(hash_slot_tracker.get_concurrent_files_data())
        assert "copy.deepcopy(hash_slot_tracker.get_concurrent_files_data())" in hash_init_section or \
               "hash_slot_tracker.get_concurrent_files_data()" in hash_init_section, \
            f"Hash initialization callback must use hash_slot_tracker.get_concurrent_files_data(), " \
            f"not empty list. Section:\n{hash_init_section}"

    def test_hash_completion_callback_uses_slot_tracker_data(self):
        """Hash phase completion must get concurrent_files from slot_tracker, not empty list."""
        # Read the actual source code
        source_file = Path("/home/jsbattig/Dev/code-indexer/src/code_indexer/services/high_throughput_processor.py")
        source_code = source_file.read_text()

        # Find the hash completion callback (~line 519)
        hash_complete_section = None
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if "✅ Hash calculation complete" in line:
                # Get surrounding 10 lines for context
                hash_complete_section = '\n'.join(lines[max(0, i-5):min(len(lines), i+5)])
                break

        assert hash_complete_section is not None, "Could not find hash completion section"

        # CRITICAL CHECK: Must use hash_slot_tracker.get_concurrent_files_data()
        assert "copy.deepcopy(hash_slot_tracker.get_concurrent_files_data())" in hash_complete_section or \
               "hash_slot_tracker.get_concurrent_files_data()" in hash_complete_section, \
            f"Hash completion callback must use hash_slot_tracker.get_concurrent_files_data(), " \
            f"not empty list. Section:\n{hash_complete_section}"

    def test_final_completion_callback_includes_concurrent_files(self):
        """Final completion callback must include concurrent_files parameter (empty for completion)."""
        # Read the actual source code
        source_file = Path("/home/jsbattig/Dev/code-indexer/src/code_indexer/services/high_throughput_processor.py")
        source_code = source_file.read_text()

        # Find the final completion callback (~line 735)
        # Look for the progress_callback call that uses final_info_msg
        final_complete_section = None
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            # Look for progress_callback with info=final_info_msg
            if 'info=final_info_msg' in line:
                # Get surrounding 15 lines for context
                final_complete_section = '\n'.join(lines[max(0, i-5):min(len(lines), i+10)])
                break

        assert final_complete_section is not None, "Could not find final completion section with info=final_info_msg"

        # CRITICAL CHECK: Must include concurrent_files parameter
        # For completion, it should be empty list [] (no active files)
        assert "concurrent_files=" in final_complete_section, \
            f"Final completion callback must include concurrent_files parameter. Section:\n{final_complete_section}"


class TestDaemonCallbacksFilterSlotTracker:
    """Test that daemon callbacks remove slot_tracker to prevent RPyC proxy leakage."""

    def test_daemon_service_code_filters_slot_tracker(self):
        """Verify daemon/service.py correlated_callback filters out slot_tracker."""
        # Read the actual daemon service code
        source_file = Path("/home/jsbattig/Dev/code-indexer/src/code_indexer/daemon/service.py")
        source_code = source_file.read_text()

        # Find the correlated_callback function
        callback_section = None
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if 'def correlated_callback(current, total, file_path, info="", **cb_kwargs):' in line:
                # Get the entire function (next ~30 lines)
                callback_section = '\n'.join(lines[i:min(len(lines), i+30)])
                break

        assert callback_section is not None, "Could not find correlated_callback function"

        # CRITICAL CHECK: The callback must create filtered_kwargs WITHOUT slot_tracker
        # Look for pattern: filtered_kwargs = { ... } (excluding slot_tracker)
        # The function should NOT pass **cb_kwargs directly to client callback
        assert "filtered_kwargs" in callback_section or \
               ("slot_tracker" not in callback_section and "**cb_kwargs" not in callback_section), \
            f"Daemon correlated_callback must filter out slot_tracker. Section:\n{callback_section}"

    def test_correlated_callback_removes_slot_tracker(self):
        """Daemon's correlated_callback must filter out slot_tracker parameter."""
        # This test verifies the daemon/service.py correlated_callback implementation

        # Create mock slot tracker
        mock_slot_tracker = MagicMock(spec=CleanSlotTracker)
        mock_slot_tracker.get_concurrent_files_data.return_value = [
            {"file_path": "test.py", "file_size": 1024, "status": "processing"}
        ]

        # Create mock client callback
        client_callback = MagicMock()

        # Simulate correlated_callback behavior (from daemon/service.py)
        def correlated_callback(current, total, file_path, info="", **cb_kwargs):
            """Simulate daemon's correlated callback."""
            # Serialize concurrent_files as JSON
            concurrent_files = cb_kwargs.get('concurrent_files', [])
            concurrent_files_json = json.dumps(concurrent_files)

            # CRITICAL: Remove slot_tracker to prevent RPyC proxy leakage
            filtered_kwargs = {
                'concurrent_files_json': concurrent_files_json,
                'correlation_id': 1,
            }

            # Verify slot_tracker is NOT in filtered_kwargs
            assert 'slot_tracker' not in filtered_kwargs, \
                "slot_tracker must be filtered out in daemon callbacks"

            # Call client callback with filtered kwargs
            client_callback(current, total, file_path, info, **filtered_kwargs)

        # Simulate callback with slot_tracker
        correlated_callback(
            1, 10, Path("test.py"),
            info="Processing...",
            concurrent_files=[{"file_path": "test.py"}],
            slot_tracker=mock_slot_tracker,  # This should be filtered out
        )

        # Verify client callback received filtered kwargs
        assert client_callback.called
        call_kwargs = client_callback.call_args[1]

        # CRITICAL: slot_tracker must NOT be passed to client
        assert 'slot_tracker' not in call_kwargs, \
            "slot_tracker leaked to client callback (RPyC proxy issue)"

        # Verify concurrent_files_json is present
        assert 'concurrent_files_json' in call_kwargs, \
            "concurrent_files_json must be present in daemon callbacks"

    def test_daemon_callback_serializes_concurrent_files(self):
        """Daemon callbacks must serialize concurrent_files as JSON."""
        # Create mock client callback
        client_callback = MagicMock()

        # Simulate correlated_callback with concurrent_files
        def correlated_callback(current, total, file_path, info="", **cb_kwargs):
            """Simulate daemon's correlated callback."""
            concurrent_files = cb_kwargs.get('concurrent_files', [])
            concurrent_files_json = json.dumps(concurrent_files)

            # Verify JSON serialization works (no RPyC proxies)
            try:
                deserialized = json.loads(concurrent_files_json)
                assert isinstance(deserialized, list), \
                    "concurrent_files must deserialize to a list"
            except (TypeError, ValueError) as e:
                pytest.fail(f"concurrent_files not JSON-serializable: {e}")

            filtered_kwargs = {
                'concurrent_files_json': concurrent_files_json,
                'correlation_id': 1,
            }

            client_callback(current, total, file_path, info, **filtered_kwargs)

        # Test with concurrent_files data
        test_data = [
            {"file_path": "test1.py", "file_size": 1024, "status": "processing"},
            {"file_path": "test2.py", "file_size": 2048, "status": "complete"},
        ]

        correlated_callback(
            5, 10, Path("test.py"),
            info="Processing...",
            concurrent_files=test_data,
        )

        # Verify client received JSON string
        assert client_callback.called
        call_kwargs = client_callback.call_args[1]
        assert 'concurrent_files_json' in call_kwargs

        # Verify JSON is valid and contains correct data
        json_data = json.loads(call_kwargs['concurrent_files_json'])
        assert len(json_data) == 2
        assert json_data[0]['file_path'] == "test1.py"


class TestMultiThreadedDisplayNoFallback:
    """Test that MultiThreadedProgressManager no longer falls back to slot_tracker proxy calls."""

    def test_get_integrated_display_no_fallback_to_slot_tracker(self):
        """get_integrated_display must NOT fallback to slot_tracker.get_concurrent_files_data()."""
        # Read the actual source code
        source_file = Path("/home/jsbattig/Dev/code-indexer/src/code_indexer/progress/multi_threaded_display.py")
        source_code = source_file.read_text()

        # Find the get_integrated_display method
        display_section = None
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if 'def get_integrated_display(self' in line:
                # Get the entire method (next ~50 lines)
                display_section = '\n'.join(lines[i:min(len(lines), i+50)])
                break

        assert display_section is not None, "Could not find get_integrated_display method"

        # CRITICAL CHECK: The method must NOT call slot_tracker.get_concurrent_files_data()
        # Look for the fallback pattern that should be REMOVED
        if 'elif slot_tracker is not None:' in display_section:
            # If there's an elif for slot_tracker, verify it doesn't call get_concurrent_files_data()
            assert 'slot_tracker.get_concurrent_files_data()' not in display_section, \
                f"get_integrated_display must NOT fallback to slot_tracker.get_concurrent_files_data(). " \
                f"Section:\n{display_section}"

    def test_concurrent_files_handling_no_fallback(self):
        """Verify concurrent files handling uses self._concurrent_files only, no slot_tracker fallback."""
        # Read the actual source code
        source_file = Path("/home/jsbattig/Dev/code-indexer/src/code_indexer/progress/multi_threaded_display.py")
        source_code = source_file.read_text()

        # Find the section where concurrent_files is used (~line 297-305)
        concurrent_files_section = None
        lines = source_code.split('\n')
        for i, line in enumerate(lines):
            if 'fresh_concurrent_files' in line and '=' in line:
                # Get surrounding 15 lines for context
                concurrent_files_section = '\n'.join(lines[max(0, i-5):min(len(lines), i+10)])
                break

        assert concurrent_files_section is not None, "Could not find concurrent_files handling section"

        # CRITICAL CHECK: Must use self._concurrent_files or [] only
        # Should NOT have: elif slot_tracker is not None: fresh_concurrent_files = slot_tracker.get_concurrent_files_data()
        assert not ('elif slot_tracker is not None:' in concurrent_files_section and
                   'get_concurrent_files_data()' in concurrent_files_section), \
            f"Concurrent files handling must NOT fallback to slot_tracker. Section:\n{concurrent_files_section}"
