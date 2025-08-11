"""
Centralized Git command runner with dubious ownership handling.

This module provides a robust way to run git commands that properly handles
the "dubious ownership" error that occurs when running under sudo or in
environments where the repository owner differs from the current user.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Union


def get_git_environment(project_dir: Path) -> Dict[str, str]:
    """
    Get environment variables for git commands to handle dubious ownership.
    
    This is critical for running under sudo or in environments where the
    repository owner differs from the current user (e.g., Docker, CI/CD,
    claude batch server).
    
    Args:
        project_dir: Path to the project directory
        
    Returns:
        Dictionary of environment variables for git commands
    """
    env = os.environ.copy()
    
    # Handle dubious ownership by setting safe.directory
    # This allows git to work even when the repo is owned by a different user
    env['GIT_CONFIG_COUNT'] = '1'
    env['GIT_CONFIG_KEY_0'] = 'safe.directory'
    env['GIT_CONFIG_VALUE_0'] = str(project_dir.resolve())
    
    # Preserve any existing GIT_CONFIG_* variables from the calling environment
    # This is important for environments like claude batch server that may set
    # their own git configuration
    config_count = 1
    for key in os.environ:
        if key.startswith('GIT_CONFIG_') and not key.startswith('GIT_CONFIG_KEY_0'):
            # Parse existing GIT_CONFIG_* variables
            if key.startswith('GIT_CONFIG_KEY_'):
                idx = key.replace('GIT_CONFIG_KEY_', '')
                if idx.isdigit() and int(idx) > 0:
                    # Shift the index to make room for our safe.directory at index 0
                    new_idx = int(idx) + 1
                    env[f'GIT_CONFIG_KEY_{new_idx}'] = os.environ[key]
                    if f'GIT_CONFIG_VALUE_{idx}' in os.environ:
                        env[f'GIT_CONFIG_VALUE_{new_idx}'] = os.environ[f'GIT_CONFIG_VALUE_{idx}']
                    config_count = max(config_count, new_idx + 1)
    
    # Update the count to reflect all config entries
    env['GIT_CONFIG_COUNT'] = str(config_count)
    
    return env


def run_git_command(
    cmd: List[str],
    cwd: Path,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    timeout: Optional[float] = None,
    **kwargs
) -> subprocess.CompletedProcess:
    """
    Run a git command with proper environment handling for dubious ownership.
    
    Args:
        cmd: Git command as a list (e.g., ["git", "status"])
        cwd: Working directory for the command
        check: Whether to raise CalledProcessError on non-zero exit
        capture_output: Whether to capture stdout and stderr
        text: Whether to decode output as text
        timeout: Optional timeout in seconds
        **kwargs: Additional arguments to pass to subprocess.run
        
    Returns:
        CompletedProcess instance with the command result
        
    Raises:
        subprocess.CalledProcessError: If check=True and command fails
        subprocess.TimeoutExpired: If timeout is exceeded
    """
    if not cmd or cmd[0] != "git":
        raise ValueError("Command must start with 'git'")
    
    # Get the proper environment with safe.directory configuration
    env = get_git_environment(cwd)
    
    # Merge any environment from kwargs if provided
    if 'env' in kwargs:
        env.update(kwargs['env'])
        kwargs.pop('env')
    
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        env=env,
        **kwargs
    )


def is_git_repository(project_dir: Path) -> bool:
    """
    Check if a directory is a git repository.
    
    This properly handles dubious ownership errors.
    
    Args:
        project_dir: Path to check
        
    Returns:
        True if the directory is a git repository, False otherwise
    """
    try:
        run_git_command(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_dir,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_current_branch(project_dir: Path) -> Optional[str]:
    """
    Get the current git branch name.
    
    Args:
        project_dir: Path to the git repository
        
    Returns:
        Branch name or None if not in a git repo or on detached HEAD
    """
    try:
        result = run_git_command(
            ["git", "branch", "--show-current"],
            cwd=project_dir,
            check=True,
        )
        branch = result.stdout.strip()
        
        if not branch:
            # Handle detached HEAD
            try:
                result = run_git_command(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=project_dir,
                    check=True,
                )
                return f"detached-{result.stdout.strip()}"
            except subprocess.CalledProcessError:
                return None
        
        return branch
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_current_commit(project_dir: Path, short: bool = False) -> Optional[str]:
    """
    Get the current commit hash.
    
    Args:
        project_dir: Path to the git repository
        short: Whether to return short hash (7 chars) or full hash
        
    Returns:
        Commit hash or None if not in a git repo
    """
    try:
        cmd = ["git", "rev-parse"]
        if short:
            cmd.append("--short")
        cmd.append("HEAD")
        
        result = run_git_command(
            cmd,
            cwd=project_dir,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None