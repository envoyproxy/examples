"""The MCP server behind Envoy in the MCP filter end-to-end test.

A minimal server built on the official MCP Python SDK (the `mcp` package, at version 2.2.0, which
the suite pins). It has one tool, `get_weather(city)`, whose result is fixed so that the client can
check it exactly, and serves it over Streamable HTTP, by default at http://127.0.0.1:8000/mcp.
docker/server_entrypoint.sh starts it before Envoy. See README.md.

The SDK serves MCP protocol version 2026-07-28 with no configuration: it answers each POST whose
MCP-Protocol-Version header is 2026-07-28 on its own, statelessly, once it has checked the request's
params._meta envelope, and its Mcp-Method and Mcp-Name headers, against the body. At that version
there is no session (no Mcp-Session-Id), no GET stream and no DELETE.

With --request-log, the server also appends one JSON object per HTTP request that it answers to
that file, so that mcp_client.py can tell which requests reached it through Envoy.

With --demo, for the developer demo (DEMO=1, demo_client.py), it also has the simulated
service-operations tools of demo_tools.py, and puts cache hints on its tools/list and
server/discover results. Without --demo, it is exactly the regression suite's server.
"""
import argparse
import json

import uvicorn
from mcp.server.mcpserver import MCPServer

SERVER_NAME = "envoy-mcp-e2e-server"
# The request headers that --request-log records, when a request has them.
LOGGED_HEADERS = ("mcp-protocol-version", "mcp-method", "mcp-name", "mcp-session-id",
                  "x-e2e-case")


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # Always the same, so mcp_client.py knows exactly what must come back through Envoy.
    return f"{city}: sunny, 22C"


def build_server(demo=False):
    """The MCP server: get_weather, and with demo=True the demo's tools and cache hints."""
    if not demo:
        server = MCPServer(SERVER_NAME)
        server.tool()(get_weather)
        return server
    # Imported here, so that the regression suite's server does not depend on the demo.
    import demo_tools
    server = MCPServer(SERVER_NAME, version=demo_tools.SERVER_VERSION,
                       instructions=demo_tools.INSTRUCTIONS, cache_hints=demo_tools.CACHE_HINTS)
    server.tool()(get_weather)
    demo_tools.register(server)
    return server


def header_dict(headers):
    """ASGI headers, a list of (name, value) byte strings, as a dict with lowercase names."""
    return {name.decode("latin-1").lower(): value.decode("latin-1") for name, value in headers}


class RequestLog:
    """ASGI middleware that appends one JSON object per HTTP request to a file.

    It writes a request's line when the response starts, so the line is in the file before the
    response can reach the client.
    """

    def __init__(self, app, path):
        self.app = app
        self.file = open(path, "a", encoding="utf-8")

    async def __call__(self, scope, receive, send):
        # Other scopes, such as the lifespan one that starts the SDK's session manager, pass by.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_headers = header_dict(scope["headers"])

        async def send_and_log(message):
            if message["type"] == "http.response.start":
                response_headers = header_dict(message.get("headers", []))
                record = {
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": message["status"],
                    "headers": {
                        name: request_headers[name]
                        for name in LOGGED_HEADERS
                        if name in request_headers
                    },
                    "response_mcp_session_id": response_headers.get("mcp-session-id"),
                }
                self.file.write(json.dumps(record) + "\n")
                self.file.flush()
            await send(message)

        await self.app(scope, receive, send_and_log)


def main():
    parser = argparse.ArgumentParser(description="The MCP server of the MCP filter E2E test.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--path", default="/mcp", help="the MCP endpoint")
    parser.add_argument(
        "--request-log", help="append one JSON object per HTTP request to this file")
    parser.add_argument(
        "--demo", action="store_true", help="add the developer demo's tools (demo_tools.py)")
    args = parser.parse_args()
    server = build_server(demo=args.demo)
    # Serve what server.run(transport="streamable-http") would, wrapped in the request log. With
    # this host, the SDK's DNS rebinding protection accepts the Host header 127.0.0.1:<any port>.
    # Docker Compose passes --host 0.0.0.0, for which the SDK turns that localhost-only protection
    # off, so that it accepts the Host header that Envoy forwards, envoy:10000.
    app = server.streamable_http_app(streamable_http_path=args.path, host=args.host)
    if args.request_log:
        app = RequestLog(app, args.request_log)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
