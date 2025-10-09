"""Unit tests for command configuration.

Tests the command classification logic that determines which commands
should execute in parallel vs sequentially.
"""

import unittest

from code_indexer.proxy.command_config import (
    PARALLEL_COMMANDS,
    SEQUENTIAL_COMMANDS,
    is_parallel_command,
    is_sequential_command,
)


class TestCommandClassification(unittest.TestCase):
    """Test command classification for parallel execution."""

    def test_parallel_commands_constant(self):
        """Test that PARALLEL_COMMANDS contains expected commands."""
        expected_commands = ['query', 'status', 'watch', 'fix-config']
        self.assertEqual(PARALLEL_COMMANDS, expected_commands)

    def test_query_is_parallel(self):
        """Test that query command is classified as parallel."""
        self.assertTrue(is_parallel_command('query'))

    def test_status_is_parallel(self):
        """Test that status command is classified as parallel."""
        self.assertTrue(is_parallel_command('status'))

    def test_watch_is_parallel(self):
        """Test that watch command is classified as parallel."""
        self.assertTrue(is_parallel_command('watch'))

    def test_fix_config_is_parallel(self):
        """Test that fix-config command is classified as parallel."""
        self.assertTrue(is_parallel_command('fix-config'))

    def test_start_is_not_parallel(self):
        """Test that start command is NOT parallel (Story 2.3)."""
        self.assertFalse(is_parallel_command('start'))

    def test_stop_is_not_parallel(self):
        """Test that stop command is NOT parallel (Story 2.3)."""
        self.assertFalse(is_parallel_command('stop'))

    def test_uninstall_is_not_parallel(self):
        """Test that uninstall command is NOT parallel (Story 2.3)."""
        self.assertFalse(is_parallel_command('uninstall'))

    def test_init_is_not_parallel(self):
        """Test that init command is NOT parallel."""
        self.assertFalse(is_parallel_command('init'))

    def test_index_is_not_parallel(self):
        """Test that index command is NOT parallel."""
        self.assertFalse(is_parallel_command('index'))

    def test_unknown_command_is_not_parallel(self):
        """Test that unknown commands are not parallel."""
        self.assertFalse(is_parallel_command('unknown-command'))

    def test_case_sensitive_matching(self):
        """Test that command matching is case-sensitive."""
        self.assertFalse(is_parallel_command('QUERY'))
        self.assertFalse(is_parallel_command('Query'))
        self.assertFalse(is_parallel_command('STATUS'))

    def test_empty_string_is_not_parallel(self):
        """Test that empty string is not parallel."""
        self.assertFalse(is_parallel_command(''))

    def test_all_parallel_commands_return_true(self):
        """Test that all commands in PARALLEL_COMMANDS return True."""
        for command in PARALLEL_COMMANDS:
            with self.subTest(command=command):
                self.assertTrue(is_parallel_command(command))


class TestSequentialCommandClassification(unittest.TestCase):
    """Test command classification for sequential execution (Story 2.3)."""

    def test_sequential_commands_constant(self):
        """Test that SEQUENTIAL_COMMANDS contains expected commands."""
        expected_commands = ['start', 'stop', 'uninstall']
        self.assertEqual(SEQUENTIAL_COMMANDS, expected_commands)

    def test_start_is_sequential(self):
        """Test that start command is classified as sequential."""
        self.assertTrue(is_sequential_command('start'))

    def test_stop_is_sequential(self):
        """Test that stop command is classified as sequential."""
        self.assertTrue(is_sequential_command('stop'))

    def test_uninstall_is_sequential(self):
        """Test that uninstall command is classified as sequential."""
        self.assertTrue(is_sequential_command('uninstall'))

    def test_query_is_not_sequential(self):
        """Test that query command is NOT sequential."""
        self.assertFalse(is_sequential_command('query'))

    def test_status_is_not_sequential(self):
        """Test that status command is NOT sequential."""
        self.assertFalse(is_sequential_command('status'))

    def test_init_is_not_sequential(self):
        """Test that init command is NOT sequential."""
        self.assertFalse(is_sequential_command('init'))

    def test_unknown_command_is_not_sequential(self):
        """Test that unknown commands are not sequential."""
        self.assertFalse(is_sequential_command('unknown-command'))

    def test_case_sensitive_matching(self):
        """Test that command matching is case-sensitive."""
        self.assertFalse(is_sequential_command('START'))
        self.assertFalse(is_sequential_command('Stop'))
        self.assertFalse(is_sequential_command('UNINSTALL'))

    def test_empty_string_is_not_sequential(self):
        """Test that empty string is not sequential."""
        self.assertFalse(is_sequential_command(''))

    def test_all_sequential_commands_return_true(self):
        """Test that all commands in SEQUENTIAL_COMMANDS return True."""
        for command in SEQUENTIAL_COMMANDS:
            with self.subTest(command=command):
                self.assertTrue(is_sequential_command(command))

    def test_parallel_and_sequential_mutually_exclusive(self):
        """Test that no command is both parallel and sequential."""
        for command in PARALLEL_COMMANDS:
            with self.subTest(command=command):
                self.assertFalse(is_sequential_command(command))

        for command in SEQUENTIAL_COMMANDS:
            with self.subTest(command=command):
                self.assertFalse(is_parallel_command(command))


if __name__ == '__main__':
    unittest.main()
