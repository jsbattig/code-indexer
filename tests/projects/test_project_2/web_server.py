"""
Test Project 2 - Simple Web Server
A basic HTTP server with routing and middleware support.
"""

import http.server
import socketserver
import json
from urllib.parse import urlparse, parse_qs


class SimpleWebServer:
    def __init__(self, port=8000):
        self.port = port
        self.routes = {}
        self.middleware = []

    def route(self, path, method="GET"):
        """Decorator to register routes."""

        def decorator(func):
            self.routes[f"{method}:{path}"] = func
            return func

        return decorator

    def add_middleware(self, middleware_func):
        """Add middleware function."""
        self.middleware.append(middleware_func)

    def create_handler(self):
        """Create request handler class."""
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.handle_request("GET")

            def do_POST(self):
                self.handle_request("POST")

            def handle_request(self, method):
                parsed_url = urlparse(self.path)
                path = parsed_url.path
                query_params = parse_qs(parsed_url.query)

                # Apply middleware
                for middleware in server.middleware:
                    result = middleware(self, method, path, query_params)
                    if result is False:
                        return

                # Find route handler
                route_key = f"{method}:{path}"
                if route_key in server.routes:
                    try:
                        response = server.routes[route_key](self, query_params)
                        self.send_response(200)
                        self.send_header("Content-type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps(response).encode())
                    except Exception as e:
                        self.send_error(500, f"Server Error: {str(e)}")
                else:
                    self.send_error(404, "Not Found")

        return Handler

    def start(self):
        """Start the web server."""
        handler = self.create_handler()
        with socketserver.TCPServer(("", self.port), handler) as httpd:
            print(f"Server running on port {self.port}")
            httpd.serve_forever()


def logging_middleware(handler, method, path, query_params):
    """Middleware to log requests."""
    print(f"[{method}] {path} - Query: {query_params}")
    return True


def main():
    """Example usage of the web server."""
    server = SimpleWebServer(8080)

    server.add_middleware(logging_middleware)

    @server.route("/")
    def home(handler, query_params):
        return {
            "message": "Welcome to Simple Web Server",
            "endpoints": ["/", "/health", "/echo"],
        }

    @server.route("/health")
    def health(handler, query_params):
        return {"status": "healthy", "timestamp": "2023-01-01T00:00:00Z"}

    @server.route("/echo")
    def echo(handler, query_params):
        return {"echo": query_params}

    print("Starting web server demo...")
    server.start()


if __name__ == "__main__":
    main()
