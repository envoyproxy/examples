"""The cases of the MCP JSON-REST bridge end-to-end test.

Each case sends requests to one of Envoy's listeners, C (the MCP filter in front of the bridge) or B
(the bridge alone), with raw HTTP or with the MCP Python SDK, and checks the answers, and what
reached the REST backend, against requirements.py. A check that names a known gap (gap="G2") is a
compliance check: its requirement says what should happen, and the gap why it does not on the
current Envoy. The expected REST answers are rest_server.py's own. See README.md.
"""
import dataclasses
import json
import urllib.parse
from typing import Callable

import mcp.types

import rest_server

PV = "2026-07-28"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
CLIENT_INFO = {"name": "envoy-mcp-rest-e2e-client", "version": "1.0.0"}
# The params._meta of a 2026-07-28 request.
META = {
    "io.modelcontextprotocol/protocolVersion": PV,
    "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
    "io.modelcontextprotocol/clientCapabilities": {},
}
TOOL_NAMES = [tool["name"] for tool in rest_server.TOOLS]


@dataclasses.dataclass
class Case:
    name: str
    what: str
    listener: str
    function: Callable


CASES = []


def case(name, what, listeners):
    """Registers a case once per listener, as name@B and name@C."""

    def register(function):
        for listener in listeners:
            CASES.append(Case(f"{name}@{listener}", what, listener, function))
        return function

    return register


# Requests.


def modern(method, request_id, params=None):
    """A 2026-07-28 request: params._meta carries the version."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {**(params or {}), "_meta": META},
    }


def headers(method, name=None, extra=()):
    """The headers of a 2026-07-28 POST: Content-Type, Accept, the MCP headers, and extra ones."""
    values = [("Content-Type", "application/json"),
              ("Accept", "application/json, text/event-stream"), ("MCP-Protocol-Version", PV),
              ("Mcp-Method", method)]
    if name is not None:
        values.append(("Mcp-Name", name))
    return values + list(extra)


def call(ctx, tool, arguments, extra=()):
    """Sends a 2026-07-28 tools/call with the right headers (plus extra ones)."""
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/call", request_id, {"name": tool, "arguments": arguments}),
                        headers("tools/call", tool, extra))
    return exchange, request_id


def rest_answer(method, raw_path, query="", body=b""):
    """What rest_server.py answers to a request: the text that a tool result must carry."""
    segments = [urllib.parse.unquote(segment) for segment in raw_path.split("/")[1:]]
    return rest_server.route(method, segments, query, body).body.decode("utf-8", "replace")


# Checks.


def error_of(exchange):
    message = exchange.json
    if isinstance(message, dict) and isinstance(message.get("error"), dict):
        return message["error"]
    return None


def result_of(exchange):
    message = exchange.json
    if isinstance(message, dict) and isinstance(message.get("result"), dict):
        return message["result"]
    return None


def expect_status(ctx, exchange, status, requirement):
    return ctx.check(f"HTTP {status}", exchange.status == status, f"HTTP {status}",
                     exchange.summary(), requirement)


def expect_error(ctx, exchange, code, requirement):
    error = error_of(exchange)
    return ctx.check(f"JSON-RPC error {code}", error is not None and error.get("code") == code,
                     f"a JSON-RPC error with code {code}", exchange.summary(), requirement)


def expect_echo_id(ctx, exchange, request_id):
    message = exchange.json if isinstance(exchange.json, dict) else {}
    got = message.get("id", "<no id>")
    ok = "id" in message and got == request_id and type(got) is type(request_id)
    return ctx.check(f"the response has the request's id, {request_id!r}", ok, repr(request_id),
                     repr(got), "JSONRPC-ECHO-ID")


def expect_result(ctx, exchange, request_id, *, result_type_gap=None):
    """A 200 JSON-RPC result with the request's id, and resultType "complete"."""
    expect_status(ctx, exchange, 200, "HTTP-JSON-RESPONSE")
    content_type = exchange.header("content-type") or ""
    ctx.check("Content-Type application/json", content_type.startswith("application/json"),
              "application/json", content_type or "none", "HTTP-JSON-RESPONSE")
    result = result_of(exchange)
    ctx.check("a JSON-RPC result", result is not None, "a result", exchange.summary(),
              "HTTP-JSON-RESPONSE")
    expect_echo_id(ctx, exchange, request_id)
    result = result or {}
    ctx.check('resultType "complete"', result.get("resultType") == "complete", '"complete"',
              repr(result.get("resultType", "<none>")), "RESULT-TYPE", result_type_gap)
    return result


def expect_tool_result(ctx, exchange, request_id, *, is_error, texts=None,
                       is_error_requirement="BRIDGE-RESPONSE"):
    """A tools/call result: text content, isError, and the schema."""
    result = expect_result(ctx, exchange, request_id)
    content = result.get("content")
    got = None
    if isinstance(content, list) and all(
            isinstance(item, dict) and item.get("type") == "text" for item in content):
        got = [item.get("text") for item in content]
    if texts is not None:
        ctx.check("the text content is the REST response", got == texts, quote(texts),
                  quote(got if got is not None else content), "BRIDGE-RESPONSE")
    ctx.check(f"isError {str(is_error).lower()}", result.get("isError") is is_error, is_error,
              result.get("isError", "<none>"), is_error_requirement)
    ctx.schema("tools/call", result)
    return result


def expect_cache_hints(ctx, result, gap=None):
    ttl = result.get("ttlMs", "<none>")
    ctx.check("ttlMs, an integer >= 0", isinstance(ttl, int) and not isinstance(ttl, bool) and
              ttl >= 0, "an integer >= 0", repr(ttl), "CACHE-HINTS", gap)
    scope = result.get("cacheScope", "<none>")
    ctx.check('cacheScope "public" or "private"', scope in ("public", "private"),
              '"public" or "private"', repr(scope), "CACHE-HINTS", gap)


def expect_server_info(ctx, result, gap=None):
    info = (result.get("_meta") or {}).get(META_SERVER_INFO)
    ok = isinstance(info, dict) and isinstance(info.get("name"), str)
    ctx.check("_meta has io.modelcontextprotocol/serverInfo", ok, "{name, version}",
              repr(info if info is not None else "<none>"), "SERVER-INFO", gap)


def expect_rest(ctx, method, raw_path, query="", *, body=None, request_headers=None,
                requirement):
    """The case's one REST request: method, raw path, query, and the body and headers given."""
    entries = ctx.backend()
    seen = [f"{e['method']} {e['raw_path']}" + (f"?{e['query']}" if e["query"] else "")
            for e in entries]
    want = f"{method} {raw_path}" + (f"?{query}" if query else "")
    ctx.check(f"the REST backend got {want}", seen == [want], [want], seen, requirement)
    if not entries:
        return
    entry = entries[-1]
    if body is not None:
        try:
            got = json.loads(entry["body"]) if entry["body"] else ""
        except ValueError:
            got = entry["body"]
        ctx.check("the REST request body", got == body, json.dumps(body), repr(entry["body"]),
                  "BRIDGE-BODY")
    for name, value in (request_headers or {}).items():
        got = entry["headers"].get(name.lower())
        ctx.check(f"the REST request has {name}: {value}", got == value, value, got, requirement)


def expect_no_rest(ctx, requirement):
    entries = ctx.backend()
    seen = [f"{e['method']} {e['raw_path']}" for e in entries]
    return ctx.check("the request did not reach the REST backend", not entries, "no REST request",
                     seen, requirement)


def quote(value, limit=200):
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "..."


def sdk_outcome(value, error):
    if error is not None:
        code = getattr(error, "code", None)
        first = (str(getattr(error, "message", None) or error).splitlines() or [""])[0]
        return f"{type(error).__name__}" + (f" {code}" if code is not None else "") + f": {first}"
    return quote(value)


# tools/list, in both of the bridge's modes.


@case("tools-list.local", "2026-07-28 tools/list, answered by the bridge (tool_list_local)",
      ("B",))
def tools_list_local(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id), headers("tools/list"))
    result = expect_result(ctx, exchange, request_id)
    ctx.check("the configured tools, with their tool_list_config, in order",
              result.get("tools") == rest_server.TOOLS, quote(TOOL_NAMES),
              quote(result.get("tools")), "BRIDGE-LOCAL-LIST")
    expect_cache_hints(ctx, result)
    ctx.schema("tools/list", result)
    expect_server_info(ctx, result, gap="G12")
    expect_no_rest(ctx, "BRIDGE-LOCAL-LIST")


@case("tools-list.http-rule", "2026-07-28 tools/list, transcoded to the REST backend's GET "
      "/v1/tools (tool_list_http_rule)", ("C",))
def tools_list_http_rule(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id), headers("tools/list"))
    result = expect_result(ctx, exchange, request_id, result_type_gap="G2")
    ctx.check("the REST backend's tools", result.get("tools") == rest_server.TOOLS,
              quote(TOOL_NAMES), quote(result.get("tools")), "BRIDGE-HTTP-LIST")
    expect_cache_hints(ctx, result, gap="G2")
    ctx.schema("tools/list", result, gap="G2")
    expect_rest(ctx, "GET", "/v1/tools", body="", requirement="BRIDGE-HTTP-LIST")


# The MCP Python SDK, through the MCP filter, the bridge and the REST backend.


@case("sdk.call-tool-direct", "the SDK's session sends tools/call without listing the tools "
      "first, and parses the result", ("C",))
def sdk_call_tool_direct(ctx):

    async def run():
        async with ctx.sdk() as client:
            request = mcp.types.CallToolRequest(params=mcp.types.CallToolRequestParams(
                name="get_weather", arguments={"city": "Paris"}))
            result = await client.session.send_request(request, mcp.types.CallToolResult)
            return result.is_error, [block.text for block in result.content]

    value, error = ctx.run_sdk(run)
    want = (False, [rest_answer("GET", "/v1/weather/Paris")])
    ctx.check("the result parses, with the REST answer", error is None and value == want,
              quote(want), sdk_outcome(value, error), "SDK-CALL")
    expect_rest(ctx, "GET", "/v1/weather/Paris", requirement="SDK-CALL")


# Mcp-Param headers: get_forecast's City (string), Days (integer) and Detailed (boolean).

FORECAST = {"city": "Paris", "days": 3, "detailed": True}
FORECAST_HEADERS = [("Mcp-Param-City", "Paris"), ("Mcp-Param-Days", "3"),
                    ("Mcp-Param-Detailed", "true")]


@case("params.valid", "get_forecast with matching Mcp-Param headers", ("B", "C"))
def params_valid(ctx):
    exchange, request_id = call(ctx, "get_forecast", FORECAST, FORECAST_HEADERS)
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       is_error_requirement="PARAM-MATCH")
    expect_rest(ctx, "GET", "/v1/forecast/Paris", "days=3&detailed=true",
                request_headers=dict(FORECAST_HEADERS), requirement="PARAM-FORWARD")


@case("params.mismatch", "Mcp-Param-City Lyon for city Paris", ("C",))
def params_mismatch(ctx):
    exchange, request_id = call(ctx, "get_forecast", FORECAST,
                                [("Mcp-Param-City", "Lyon"), *FORECAST_HEADERS[1:]])
    expect_status(ctx, exchange, 400, "PARAM-MATCH")
    expect_error(ctx, exchange, -32020, "PARAM-MATCH")
    expect_echo_id(ctx, exchange, request_id)
    expect_no_rest(ctx, "PARAM-MATCH")


# Transcoding of requests and responses.


@case("transcoding.get", "get_weather: path variable, and the other arguments as the query",
      ("B", "C"))
def transcoding_get(ctx):
    exchange, request_id = call(ctx, "get_weather", {"city": "Paris", "units": "imperial"})
    result = expect_tool_result(
        ctx, exchange, request_id, is_error=False,
        texts=[rest_answer("GET", "/v1/weather/Paris", "units=imperial")])
    expect_rest(ctx, "GET", "/v1/weather/Paris", "units=imperial", body="",
                requirement="BRIDGE-QUERY")
    expect_server_info(ctx, result, gap="G12")


@case("transcoding.body-star", "create_order: body \"*\"", ("C",))
def transcoding_body_star(ctx):
    arguments = {"item": "widget", "quantity": 3, "options": {"gift": True}}
    exchange, request_id = call(ctx, "create_order", arguments)
    answer = rest_answer("POST", "/v1/orders", body=json.dumps(arguments).encode())
    expect_tool_result(ctx, exchange, request_id, is_error=False, texts=[answer])
    expect_rest(ctx, "POST", "/v1/orders", body=arguments, request_headers={
        "content-type": "application/json"
    }, requirement="BRIDGE-BODY")


@case("transcoding.streaming", "stream_text: a chunked REST answer, streamed", ("C",))
def transcoding_streaming(ctx):
    exchange, request_id = call(ctx, "stream_text", {})
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       texts=[b"".join(rest_server.TEXT_CHUNKS).decode()],
                       is_error_requirement="BRIDGE-STREAMING")


# An empty POST, which the bridge alone must answer (on listener C, the MCP filter rejects it).


@case("errors.empty-body", "a POST with an empty body", ("B",))
def errors_empty_body(ctx):
    exchange = ctx.post(raw=b"", headers=headers("tools/list"), timeout=5)
    expect_status(ctx, exchange, 400, "BRIDGE-EMPTY-BODY")
    expect_error(ctx, exchange, -32700, "JSONRPC-PARSE")
