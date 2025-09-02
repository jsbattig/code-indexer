"""
Main entry point for CIDX Server.

Runs FastAPI server using uvicorn with proper configuration.
"""

import argparse
import uvicorn
from pathlib import Path


def main():
    """Main entry point for CIDX server."""
    parser = argparse.ArgumentParser(description="CIDX Multi-User Server")
    parser.add_argument(
        "--port", type=int, default=8090, help="Port to run server on (default: 8090)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind server to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    # Ensure ~/.cidx-server directory exists
    server_dir = Path.home() / ".cidx-server"
    server_dir.mkdir(exist_ok=True)

    print(f"Starting CIDX Server on {args.host}:{args.port}")
    print(f"Server directory: {server_dir}")
    print(f"Documentation available at: http://{args.host}:{args.port}/docs")
    print("Press Ctrl+C to stop the server")

    # Run server
    uvicorn.run(
        "code_indexer.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=True,
    )


if __name__ == "__main__":
    main()
