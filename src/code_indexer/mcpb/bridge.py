"""Main bridge module connecting stdin/stdout to CIDX server.

This module implements the main bridge loop that reads JSON-RPC requests from stdin,
forwards them to the CIDX server via HTTP, and writes responses to stdout.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TextIO, Optional

from .config import BridgeConfig
from .diagnostics import diagnose_configuration
from .http_client import BridgeHttpClient, HttpError, TimeoutError
from .protocol import (
    parse_jsonrpc_request,
    create_error_response,
    PARSE_ERROR,
    INVALID_REQUEST,
    SERVER_ERROR,
)


class Bridge:
    """MCP Stdio Bridge - forwards JSON-RPC requests to CIDX server.

    Args:
        config: Bridge configuration
        config_path: Path to config file for token persistence (optional)
    """

    def __init__(self, config: BridgeConfig, config_path: Optional[Path] = None):
        self.config = config
        self.http_client = BridgeHttpClient(
            server_url=config.server_url,
            bearer_token=config.bearer_token,
            timeout=config.timeout,
            refresh_token=config.refresh_token,
            config_path=config_path,
        )

    async def process_line(self, line: str) -> dict:
        """Process a single line of input containing JSON-RPC request.

        Args:
            line: JSON string containing JSON-RPC request

        Returns:
            JSON-RPC response as dictionary
        """
        print(f"DEBUG process_line: Received line: {repr(line[:200] if len(line) > 200 else line)}", file=sys.stderr)
        try:
            # Parse JSON-RPC request
            request = parse_jsonrpc_request(line)
            return await self.process_request(request.to_dict())

        except json.JSONDecodeError as e:
            # Return parse error
            # MCP protocol requires ID to be string/number, NOT null
            # Use 0 per MCP spec when request ID cannot be determined
            error_response = create_error_response(
                request_id=0,
                code=PARSE_ERROR,
                message="Parse error",
                data={"detail": str(e)},
            )
            return error_response.to_dict()

        except ValueError as e:
            # Return invalid request error
            # MCP protocol requires ID to be string/number, NOT null
            # Use 0 per MCP spec when request ID cannot be determined
            error_response = create_error_response(
                request_id=0,
                code=INVALID_REQUEST,
                message="Invalid Request",
                data={"detail": str(e)},
            )
            return error_response.to_dict()

    async def process_request(self, request_data: dict) -> dict:
        """Process a JSON-RPC request dictionary.

        Args:
            request_data: JSON-RPC request as dictionary

        Returns:
            JSON-RPC response as dictionary
        """
        request_id = request_data.get("id")

        try:
            # Validate request has required fields
            if "method" not in request_data:
                error_response = create_error_response(
                    request_id=request_id,
                    code=INVALID_REQUEST,
                    message="Invalid Request: missing 'method' field",
                )
                return error_response.to_dict()

            # Forward request to CIDX server
            response_data = await self.http_client.forward_request(request_data)
            return response_data

        except TimeoutError as e:
            # Return timeout error
            error_response = create_error_response(
                request_id=request_id,
                code=SERVER_ERROR,
                message=f"Request timed out: {str(e)}",
            )
            return error_response.to_dict()

        except HttpError as e:
            # Return transport/server error
            error_response = create_error_response(
                request_id=request_id, code=SERVER_ERROR, message=str(e)
            )
            return error_response.to_dict()

        except Exception as e:
            # Return internal error
            error_response = create_error_response(
                request_id=request_id,
                code=SERVER_ERROR,
                message=f"Internal error: {str(e)}",
            )
            return error_response.to_dict()

    async def run_stdio_loop(
        self, stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None
    ):
        """Run main stdio loop - read from stdin, write to stdout.

        Args:
            stdin: Input stream (default: sys.stdin)
            stdout: Output stream (default: sys.stdout)
        """
        if stdin is None:
            stdin = sys.stdin
        if stdout is None:
            stdout = sys.stdout

        try:
            for line in stdin:
                line = line.strip()
                if not line:
                    continue

                # Process request
                response = await self.process_line(line)

                # Write response to stdout
                json_response = json.dumps(response)
                stdout.write(json_response + "\n")
                stdout.flush()

        finally:
            await self.http_client.close()

    async def run(self):
        """Run bridge with default stdin/stdout."""
        await self.run_stdio_loop()


def setup_credentials_command():  # pragma: no cover
    """CLI command to set up encrypted credentials for automatic login."""
    import getpass
    from .credential_storage import save_credentials

    print("MCPB Credential Setup")
    print("=" * 40)
    print("Enter credentials for automatic login when tokens expire.")
    print("Credentials will be stored encrypted in ~/.mcpb/\n")

    username = input("Username: ").strip()
    if not username:
        print("Error: Username cannot be empty", file=sys.stderr)
        return 1

    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password cannot be empty", file=sys.stderr)
        return 1

    # Confirm password
    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("Error: Passwords do not match", file=sys.stderr)
        return 1

    try:
        save_credentials(username, password)
        print("\nCredentials saved successfully to ~/.mcpb/credentials.enc")
        print("  Encryption key: ~/.mcpb/encryption.key")
        print("  File permissions: 600 (owner read/write only)")
        print("\nAuto-login will be attempted when tokens expire.")
        return 0
    except Exception as e:
        print(f"Error saving credentials: {str(e)}", file=sys.stderr)
        return 1


async def async_main():  # pragma: no cover
    """Async main entry point for bridge executable."""
    from .config import load_config, DEFAULT_CONFIG_PATH

    print(f"DEBUG: HOME={os.environ.get('HOME')}", file=sys.stderr)
    print(f"DEBUG: PYTHONPATH={os.environ.get('PYTHONPATH')}", file=sys.stderr)
    print(f"DEBUG: PYTHONUNBUFFERED={os.environ.get('PYTHONUNBUFFERED')}", file=sys.stderr)
    print(f"DEBUG: DEFAULT_CONFIG_PATH={DEFAULT_CONFIG_PATH}", file=sys.stderr)

    try:
        # Determine config path (None if using only env vars)
        config_path = None
        if not (os.environ.get("CIDX_SERVER_URL") or os.environ.get("MCPB_SERVER_URL")):
            # Not using env vars, so config file exists
            config_path = DEFAULT_CONFIG_PATH

        # Load configuration
        config = load_config(config_path=config_path, use_env=True)

        # Create and run bridge
        bridge = Bridge(config, config_path=config_path)
        await bridge.run()

    except FileNotFoundError as e:
        print(f"MCPB Configuration Error: {str(e)}", file=sys.stderr)
        print("Expected config file location: ~/.mcpb/config.json", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"MCPB Fatal Error: {str(e)}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def main():  # pragma: no cover
    """Synchronous wrapper for CLI entry point with argument parsing."""
    from code_indexer import __version__

    parser = argparse.ArgumentParser(
        description="MCP Stdio Bridge - Forward JSON-RPC requests to CIDX server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Run configuration diagnostics and exit",
    )

    parser.add_argument(
        "--config",
        type=str,
        metavar="PATH",
        help="Path to configuration file (default: ~/.mcpb/config.json)",
    )

    parser.add_argument(
        "--setup-credentials",
        action="store_true",
        help="Set up encrypted credentials for automatic login",
    )

    args = parser.parse_args()

    # Handle --setup-credentials flag
    if args.setup_credentials:
        sys.exit(setup_credentials_command())

    # Handle --diagnose flag
    if args.diagnose:
        try:
            result = diagnose_configuration(config_path=args.config, use_env=True)
            print(result.format_output())
            sys.exit(0)
        except Exception as e:
            print(f"Diagnostics failed: {str(e)}", file=sys.stderr)
            sys.exit(1)

    # Normal bridge operation
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
