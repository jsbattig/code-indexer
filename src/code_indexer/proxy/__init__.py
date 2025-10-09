"""Proxy mode functionality for managing multiple indexed repositories."""

from .proxy_initializer import (
    ProxyInitializer,
    ProxyInitializationError,
    NestedProxyError,
)
from .parallel_executor import ParallelCommandExecutor
from .sequential_executor import SequentialCommandExecutor, SequentialExecutionResult
from .command_config import (
    PARALLEL_COMMANDS,
    SEQUENTIAL_COMMANDS,
    is_parallel_command,
    is_sequential_command,
)
from .command_validator import (
    PROXIED_COMMANDS,
    UnsupportedProxyCommandError,
    validate_proxy_command,
    is_supported_proxy_command,
)
from .result_aggregator import ParallelResultAggregator
from .cli_integration import execute_proxy_command
from .watch_manager import ParallelWatchManager
from .output_multiplexer import OutputMultiplexer
from .repository_formatter import RepositoryPrefixFormatter

__all__ = [
    "ProxyInitializer",
    "ProxyInitializationError",
    "NestedProxyError",
    "ParallelCommandExecutor",
    "SequentialCommandExecutor",
    "SequentialExecutionResult",
    "PARALLEL_COMMANDS",
    "SEQUENTIAL_COMMANDS",
    "PROXIED_COMMANDS",
    "is_parallel_command",
    "is_sequential_command",
    "validate_proxy_command",
    "is_supported_proxy_command",
    "UnsupportedProxyCommandError",
    "ParallelResultAggregator",
    "execute_proxy_command",
    "ParallelWatchManager",
    "OutputMultiplexer",
    "RepositoryPrefixFormatter",
]
