"""The REST backend of the MCP JSON-REST bridge end-to-end test.

A REST API with deterministic answers, behind Envoy's MCP JSON-REST bridge, which transcodes MCP
tools/list and tools/call requests into requests to it. It has one route per tool of envoy.yaml,
and GET /v1/tools, which lists those tools for the bridge's tool_list_http_rule.

It appends one JSON object per request to its request log: method, raw path (as the bridge sent
it), query, headers and body. The bridge forwards the client's headers, so each entry has the
X-E2E-Case header of the case that caused it. Plain ASGI on uvicorn, which the mcp==2.2.0 image
has. See README.md.
"""
import argparse
import json
import urllib.parse

import uvicorn

# GET /v1/tools: the tools of envoy.yaml, in its order, with the descriptions and input schemas of
# its tool_list_config, as an MCP ListToolsResult in the shape of protocol version 2025-11-25: the
# schema that the bridge's API docs require of tool_list_http_rule's backend. It has none of the
# fields that protocol version 2026-07-28 adds (resultType, ttlMs, cacheScope).
TOOLS = [
    {
        "name": "get_weather",
        "title": "Weather",
        "description": "The current weather in a city.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "units": {"type": "string", "enum": ["metric", "imperial"]},
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_forecast",
        "description": "The weather forecast for a city.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "x-mcp-header": "City"},
                "days": {"type": "integer", "x-mcp-header": "Days"},
                "detailed": {"type": "boolean", "x-mcp-header": "Detailed"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "create_order",
        "description": "Creates an order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "quantity": {"type": "integer"},
                "options": {"type": "object"},
            },
            "required": ["item", "quantity"],
        },
    },
    {
        # envoy.yaml gives it no input_schema: the bridge's default.
        "name": "stream_text",
        "description": "A chunked JSON answer, streamed.",
        "inputSchema": {"type": "object"},
    },
]

# The chunks of GET /v1/stream/text.
TEXT_CHUNKS = (b'{"chunks":', b'["one","two",', b'"three"]}')


def compact(value):
    """JSON, compact and with sorted keys, so that answers are byte-for-byte deterministic."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def json_body(body):
    """The request body as JSON, or its text if it is not JSON, or None if there is none."""
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return body.decode("utf-8", "replace")


class Response:
    """A response: status, and a JSON body, or chunks to send one at a time (streaming)."""

    def __init__(self, status, value=None, chunks=None):
        self.status = status
        self.chunks = chunks
        self.body = b"" if chunks is not None else compact(value)
        self.headers = [("content-type", "application/json")]
        if chunks is None:
            self.headers.append(("content-length", str(len(self.body))))


def capture(segments, *pattern):
    """The segments in pattern's None places, if the segments match the pattern, or None."""
    if len(segments) != len(pattern):
        return None
    values = []
    for segment, part in zip(segments, pattern):
        if part is None:
            values.append(segment)
        elif segment != part:
            return None
    return values


def route(method, segments, query, body):
    """The answer to a request. segments: the percent-decoded segments of the raw path."""
    params = urllib.parse.parse_qsl(query, keep_blank_values=True)
    get = method == "GET"
    if get and capture(segments, "v1", "tools") is not None:
        return Response(200, {"tools": TOOLS})
    city = capture(segments, "v1", "weather", None)
    if get and city is not None:
        units = dict(params).get("units", "metric")
        weather = {"conditions": "sunny", "temperature": 22, "units": units}
        return Response(200, {"city": city[0]} | weather)
    city = capture(segments, "v1", "forecast", None)
    if get and city is not None:
        return Response(200, {"city": city[0], "forecast": ["sunny", "cloudy"], "query": params})
    if method == "POST" and capture(segments, "v1", "orders") is not None:
        return Response(201, {"id": "order-1", "created": json_body(body)})
    if get and capture(segments, "v1", "stream", "text") is not None:
        return Response(200, chunks=TEXT_CHUNKS)
    return Response(404, {"error": "no such route", "method": method, "path": "/".join(segments)})


class App:
    """The ASGI app: reads the whole body, answers, and logs the request as the response starts."""

    def __init__(self, request_log):
        self.log = open(request_log, "a", encoding="utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        headers = {}
        for name, value in scope["headers"]:
            name, value = name.decode("latin-1").lower(), value.decode("latin-1")
            headers[name] = value if name not in headers else f"{headers[name]}, {value}"
        raw_path = scope["raw_path"].decode("latin-1")
        segments = [urllib.parse.unquote(segment) for segment in raw_path.split("/")[1:]]
        query = scope["query_string"].decode("latin-1")
        response = route(scope["method"], segments, query, body)
        self.log.write(
            json.dumps({
                "e2e_case": headers.get("x-e2e-case"),
                "method": scope["method"],
                "raw_path": raw_path,
                "query": query,
                "headers": headers,
                "body": body.decode("utf-8", "replace"),
                "status": response.status,
            }) + "\n")
        self.log.flush()
        await send({
            "type": "http.response.start",
            "status": response.status,
            "headers": [(name.encode(), value.encode()) for name, value in response.headers],
        })
        if response.chunks is None:
            await send({"type": "http.response.body", "body": response.body})
            return
        for chunk in response.chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b""})


def main():
    parser = argparse.ArgumentParser(description="The REST backend of the bridge E2E test.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--request-log", required=True, help="JSONL file of the requests")
    args = parser.parse_args()
    uvicorn.run(App(args.request_log), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
