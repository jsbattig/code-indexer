"""Test to ensure no dead code exists in CLI module."""


def test_no_perform_complete_system_wipe_function():
    """Verify the dead _perform_complete_system_wipe function has been removed."""
    from src.code_indexer import cli

    # This function should not exist - it was dead code
    assert not hasattr(
        cli, "_perform_complete_system_wipe"
    ), "_perform_complete_system_wipe is dead code and should be removed"
