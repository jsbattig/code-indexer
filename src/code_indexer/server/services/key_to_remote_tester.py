"""
Key-to-Remote Tester Service.

Tests SSH key authentication against remote hosts.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class TestResult:
    """Result of an SSH authentication test."""

    success: bool
    message: str
    timed_out: bool = False


class KeyToRemoteTester:
    """
    Service for testing SSH key authentication against remote hosts.

    Uses ssh -T command to test if a key can authenticate to a git host.
    """

    def __init__(self, timeout_seconds: int = 10):
        """
        Initialize the key tester.

        Args:
            timeout_seconds: Timeout for SSH connection attempts
        """
        self.timeout_seconds = timeout_seconds

    def test_key_against_host(self, key_path: Path, hostname: str) -> TestResult:
        """
        Test if an SSH key can authenticate to a host.

        Args:
            key_path: Path to the private SSH key
            hostname: Hostname to test against (e.g., github.com)

        Returns:
            TestResult with success status and message
        """
        command = [
            "ssh",
            "-T",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout_seconds}",
            "-o", "StrictHostKeyChecking=accept-new",
            "-i", str(key_path),
            f"git@{hostname}",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 5,
            )

            return self._parse_ssh_output(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        except subprocess.TimeoutExpired:
            return TestResult(
                success=False,
                message="Connection timed out",
                timed_out=True,
            )

        except Exception as e:
            return TestResult(
                success=False,
                message=str(e),
            )

    def test_key_against_multiple_hosts(
        self,
        key_path: Path,
        hostnames: List[str],
    ) -> Dict[str, TestResult]:
        """
        Test an SSH key against multiple hosts.

        Args:
            key_path: Path to the private SSH key
            hostnames: List of hostnames to test

        Returns:
            Dict mapping hostname to TestResult
        """
        results = {}
        for hostname in hostnames:
            results[hostname] = self.test_key_against_host(key_path, hostname)
        return results

    def _parse_ssh_output(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> TestResult:
        """
        Parse SSH command output to determine authentication success.

        Args:
            exit_code: SSH command exit code
            stdout: Standard output
            stderr: Standard error

        Returns:
            TestResult with parsed success status
        """
        combined = (stdout + stderr).lower()

        # Check for success indicators
        # GitHub: "Hi user! You've successfully authenticated..."
        # GitLab: "Welcome to GitLab, @user!"
        success_indicators = [
            "successfully authenticated",
            "welcome to gitlab",
            "hi ",  # GitHub starts with "Hi username!"
        ]

        # Check if any success indicator is present
        for indicator in success_indicators:
            if indicator in combined:
                # For "hi " we need to verify it's from GitHub
                if indicator == "hi " and "github" not in combined.lower():
                    # Check for the full pattern
                    if "you've successfully" not in combined:
                        continue
                return TestResult(
                    success=True,
                    message=stdout or stderr,
                )

        # Check for permission denied
        if "permission denied" in combined:
            return TestResult(
                success=False,
                message="Permission denied - key not authorized",
            )

        # Default to failure with original message
        return TestResult(
            success=False,
            message=stderr or stdout or f"SSH failed with exit code {exit_code}",
        )
