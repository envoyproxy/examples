"""The REST backend of the MCP JSON-REST bridge end-to-end test.

A REST API with deterministic answers, behind Envoy's MCP JSON-REST bridge, which transcodes MCP
tools/list and tools/call requests into requests to it. It has one route per tool of envoy.yaml,
and GET /v1/tools, which lists those tools for the bridge's tool_list_http_rule.

It routes on the raw request path, so that it sees percent-encoded slashes as the bridge sent them,
and it appends one JSON object per request to its request log: method, raw path, query, headers and
body. The bridge forwards the client's headers, so each entry has the X-E2E-Case header of the case
that caused it. Plain ASGI on uvicorn, which the mcp==2.2.0 image has. See README.md.
"""
import argparse
import json
import urllib.parse

import uvicorn

# GET /v1/tools: the tools of envoy.yaml, with the descriptions and input schemas of its
# tool_list_config, as an MCP ListToolsResult in the shape of protocol version 2025-11-25: the
# schema that the bridge's API docs require of tool_list_http_rule's backend. It has none of the
# fields that protocol version 2026-07-28 adds (resultType, ttlMs, cacheScope).
_OBJECT = {"type": "object"}
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
        "name": "search_items",
        "description": "Searches the catalog.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "filter": {
                    "type": "object",
                    "properties": {"color": {"type": "string"}, "size": {"type": "string"}},
                },
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
                "exact": {"type": "boolean"},
            },
            "required": ["q"],
        },
    },
    {
        "name": "get_file",
        "description": "A file, by its resource name projects/{project}/files/{file}.",
        "inputSchema": {
            "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]
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
        "name": "update_order",
        "description": "Replaces an order.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "order": {"type": "object"},
                "notify": {"type": "boolean"},
            },
            "required": ["order_id", "order"],
        },
    },
    {
        "name": "patch_order",
        "description": "Updates fields of an order.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "status": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "delete_order",
        "description": "Deletes an order.",
        "inputSchema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_account",
        "description": "The account of an API key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "session_id": {"type": "string"},
                "verbose": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_status",
        "description": "Answers with the HTTP status code it is given.",
        "inputSchema": {
            "type": "object", "properties": {"code": {"type": "integer"}}, "required": ["code"]
        },
    },
    {
        "name": "get_binary",
        "description": "Answers with bytes that are not UTF-8.",
        "inputSchema": _OBJECT,
    },
    {
        "name": "get_large",
        "description": "Answers with more than the bridge's 1 MiB response limit.",
        "inputSchema": _OBJECT,
    },
    {
        "name": "probe_method",
        "description": "Echoes the HTTP method of the REST request.",
        "inputSchema": _OBJECT,
    },
    {
        "name": "stream_text",
        "description": "A chunked JSON answer, streamed.",
        "inputSchema": _OBJECT,
    },
    {
        "name": "stream_events",
        "description": "A server-sent events answer, streamed.",
        "inputSchema": _OBJECT,
    },
    {
        "name": "stream_status",
        "description": "get_status, streamed.",
        "inputSchema": {
            "type": "object", "properties": {"code": {"type": "integer"}}, "required": ["code"]
        },
    },
]

# The API key that GET /v1/account accepts.
API_KEY = "e2e-key"
# GET /v1/large: more than the bridge's default max_response_body_size, 1 MiB.
LARGE_BYTES = 1200 * 1024
# Statuses whose responses have no body.
BODYLESS_STATUSES = (204, 304)
# The chunks of GET /v1/stream/text, and the events of GET /v1/stream/events.
TEXT_CHUNKS = (b'{"chunks":', b'["one","two",', b'"three"]}')
SSE_EVENTS = (b'data: {"event":1}\n\n', b'data: {"event":2}\n\n')


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
    """A response: status, headers, and a body, or chunks to send one at a time (streaming)."""

    def __init__(self, status, value=None, headers=(), raw=None, chunks=None, content_type=None):
        self.status = status
        self.headers = list(headers)
        self.chunks = chunks
        if chunks is not None:
            self.body = b""
            self.headers.append(("content-type", content_type or "application/json"))
            return
        if raw is not None:
            self.body = raw
        elif value is not None:
            self.body = compact(value)
        else:
            self.body = b""
        if status not in BODYLESS_STATUSES:
            self.headers.append(("content-type", content_type or "application/json"))
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


def route(method, segments, query, headers, body):
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
    if get and capture(segments, "v1", "search") is not None:
        return Response(200, {"query": params})
    file = capture(segments, "v1", "projects", None, "files", None)
    if get and file is not None:
        return Response(200, {"name": f"projects/{file[0]}/files/{file[1]}"})
    if method == "POST" and capture(segments, "v1", "orders") is not None:
        return Response(201, {"id": "order-1", "created": json_body(body)})
    order = capture(segments, "v1", "orders", None)
    if order is not None and method == "PUT":
        return Response(200, {"id": order[0], "replaced": json_body(body), "query": params})
    if order is not None and method == "PATCH":
        return Response(200, {"id": order[0], "patched": json_body(body)})
    if order is not None and method == "DELETE":
        return Response(204)
    if get and capture(segments, "v1", "account") is not None:
        return account(headers, params)
    code = capture(segments, "v1", "status", None)
    if get and code is not None and code[0].isdigit():
        return status(int(code[0]))
    if get and capture(segments, "v1", "binary") is not None:
        return Response(200, raw=b"\xff\xfe\xfd not UTF-8", content_type="application/octet-stream")
    if get and capture(segments, "v1", "large") is not None:
        return Response(200, {"data": "x" * LARGE_BYTES})
    if capture(segments, "v1", "method-probe") is not None:
        return Response(200, {"method": method})
    if get and capture(segments, "v1", "stream", "text") is not None:
        return Response(200, chunks=TEXT_CHUNKS)
    if get and capture(segments, "v1", "stream", "events") is not None:
        return Response(200, chunks=SSE_EVENTS, content_type="text/event-stream")
    return Response(404, {"error": "no such route", "method": method, "path": "/".join(segments)})


def account(headers, params):
    """GET /v1/account: 401 with no API key, 403 with a wrong one."""
    key = headers.get("x-api-key")
    if key is None:
        return Response(
            401, {"error": "missing API key"}, headers=[("www-authenticate", 'Bearer realm="e2e"')])
    if key != API_KEY:
        return Response(
            403, {"error": "forbidden"},
            headers=[("www-authenticate", 'Bearer error="insufficient_scope"')])
    return Response(200, {"account": "e2e", "cookie": headers.get("cookie"), "query": params})


def status(code):
    """GET /v1/status/{code}: that status, with a JSON body unless the status has none."""
    if code in BODYLESS_STATUSES:
        return Response(code)
    headers = [("www-authenticate", 'Bearer realm="e2e"')] if code == 401 else []
    return Response(code, {"status": code}, headers=headers)


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
        response = route(scope["method"], segments, query, headers, body)
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
