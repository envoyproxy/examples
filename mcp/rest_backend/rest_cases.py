"""The cases of the MCP JSON-REST bridge end-to-end test.

Each case sends requests to one of Envoy's listeners, C (the MCP filter in front of the bridge) or B
(the bridge alone), with raw HTTP or with the MCP Python SDK, and checks the answers, and what
reached the REST backend, against requirements.py. A check that names a known gap (gap="G2") is a
compliance check: its requirement says what should happen, and the gap why it does not on the
current Envoy. A check that names a diagnostic (diagnostic="G9") records how the bridge alone
behaves where the MCP filter in front of it meets the requirement: it never fails the run. The
expected REST answers are rest_server.py's own. See README.md.
"""
import base64
import dataclasses
import json
import urllib.parse
from typing import Callable

import mcp.types
from mcp import MCPError
from mcp.shared.inbound import mcp_param_headers, x_mcp_header_map

import rest_server

PV = "2026-07-28"
LEGACY_PV = "2025-11-25"
LEGACY_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_INFO = "io.modelcontextprotocol/clientInfo"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
CLIENT_INFO = {"name": "envoy-mcp-rest-e2e-client", "version": "1.0.0"}
TOOL_NAMES = [tool["name"] for tool in rest_server.TOOLS]
# A message without an id: a notification.
NO_ID = object()


@dataclasses.dataclass
class Case:
    name: str
    area: str
    what: str
    listener: str | None
    function: Callable


CASES = []


def case(name, area, what, listeners=("C",)):
    """Registers a case once per listener, as name@B and name@C."""

    def register(function):
        for listener in listeners:
            CASES.append(Case(f"{name}@{listener}", area, what, listener, function))
        return function

    return register


# Requests.


def meta(version=PV, *, capabilities=True, info=True, **extra):
    """The params._meta of a 2026-07-28 request."""
    value = {} if version is None else {META_VERSION: version}
    if info:
        value[META_INFO] = CLIENT_INFO
    if capabilities:
        value[META_CAPABILITIES] = {}
    return value | extra


def modern(method, request_id, params=None, meta_value=None):
    """A 2026-07-28 request (or, with NO_ID, notification): params._meta carries the version."""
    message = {"jsonrpc": "2.0"}
    if request_id is not NO_ID:
        message["id"] = request_id
    message["method"] = method
    message["params"] = {**(params or {}), "_meta": meta() if meta_value is None else meta_value}
    return message


def legacy(method, request_id, params=None):
    """A legacy (initialize-era) request: no params._meta."""
    message = {"jsonrpc": "2.0"}
    if request_id is not NO_ID:
        message["id"] = request_id
    message["method"] = method
    if params is not None:
        message["params"] = params
    return message


def headers(method=None, name=None, version=PV, extra=()):
    """The headers of an MCP POST: Content-Type, Accept, and the MCP headers given."""
    values = [("Content-Type", "application/json"),
              ("Accept", "application/json, text/event-stream")]
    if version is not None:
        values.append(("MCP-Protocol-Version", version))
    if method is not None:
        values.append(("Mcp-Method", method))
    if name is not None:
        values.append(("Mcp-Name", name))
    return values + list(extra)


def call(ctx, tool, arguments, *, extra=(), meta_value=None, request_id=None, name=None):
    """Sends a 2026-07-28 tools/call with the right headers (plus extra ones)."""
    request_id = ctx.next_id() if request_id is None else request_id
    params = {"name": tool} if arguments is None else {"name": tool, "arguments": arguments}
    exchange = ctx.post(
        modern("tools/call", request_id, params, meta_value),
        headers("tools/call", tool if name is None else name, extra=extra))
    return exchange, request_id


def legacy_call(ctx, tool, arguments, version=LEGACY_PV, extra=()):
    request_id = ctx.next_id()
    exchange = ctx.post(
        legacy("tools/call", request_id, {"name": tool, "arguments": arguments}),
        headers(version=version, extra=extra))
    return exchange, request_id


def rest_answer(method, raw_path, query="", request_headers=None, body=b""):
    """What rest_server.py answers to a request: the text that a tool result must carry."""
    segments = [urllib.parse.unquote(segment) for segment in raw_path.split("/")[1:]]
    response = rest_server.route(method, segments, query, request_headers or {}, body)
    return response.body.decode("utf-8", "replace")


def tool_schema(name):
    return next(tool["inputSchema"] for tool in rest_server.TOOLS if tool["name"] == name)


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


def expect_status(ctx, exchange, statuses, requirement, gap=None):
    statuses = statuses if isinstance(statuses, tuple) else (statuses,)
    wanted = " or ".join(map(str, statuses))
    return ctx.check(f"HTTP {wanted}", exchange.status in statuses, f"HTTP {wanted}",
                     exchange.summary(), requirement, gap)


def expect_error(ctx, exchange, codes, requirement, gap=None, diagnostic=None):
    """A JSON-RPC error with one of codes, or with codes None, any JSON-RPC error."""
    error = error_of(exchange)
    if codes is None:
        ok = error is not None and isinstance(error.get("code"), int)
        return ctx.check("a JSON-RPC error", ok, "a JSON-RPC error", exchange.summary(),
                         requirement, gap, diagnostic)
    codes = codes if isinstance(codes, tuple) else (codes,)
    wanted = " or ".join(map(str, codes))
    return ctx.check(f"JSON-RPC error {wanted}", error is not None and error.get("code") in codes,
                     f"a JSON-RPC error with code {wanted}", exchange.summary(), requirement, gap,
                     diagnostic)


def expect_modern_code(ctx, exchange):
    """The error's code is not from the legacy range, -32000 to -32019."""
    code = (error_of(exchange) or {}).get("code")
    ctx.check("the error code is not a legacy one (-32000 to -32019)",
              isinstance(code, int) and not -32019 <= code <= -32000, "not -32000..-32019", code,
              "ERROR-CODE-RANGE", gap="G13")


def expect_echo_id(ctx, exchange, request_id):
    message = exchange.json if isinstance(exchange.json, dict) else {}
    got = message.get("id", "<no id>")
    ok = "id" in message and got == request_id and type(got) is type(request_id)
    return ctx.check(f"the response has the request's id, {request_id!r}", ok, repr(request_id),
                     repr(got), "JSONRPC-ECHO-ID")


def expect_no_id(ctx, exchange, gap=None):
    message = exchange.json
    ok = isinstance(message, dict) and "id" not in message
    actual = f"id {message['id']!r}" if isinstance(message, dict) and "id" in message else (
        exchange.summary())
    return ctx.check("the error response has no id member", ok, "no id member", actual,
                     "JSONRPC-NO-ID", gap)


def expect_result(ctx, exchange, request_id, *, stateless=True, result_type_gap=None):
    """A 200 JSON-RPC result with the request's id, and resultType "complete" if stateless."""
    expect_status(ctx, exchange, 200, "HTTP-JSON-RESPONSE")
    content_type = exchange.header("content-type") or ""
    ctx.check("Content-Type application/json", content_type.startswith("application/json"),
              "application/json", content_type or "none", "HTTP-JSON-RESPONSE")
    result = result_of(exchange)
    ctx.check("a JSON-RPC result", result is not None, "a result", exchange.summary(),
              "HTTP-JSON-RESPONSE")
    expect_echo_id(ctx, exchange, request_id)
    result = result or {}
    if stateless:
        ctx.check('resultType "complete"', result.get("resultType") == "complete", '"complete"',
                  repr(result.get("resultType", "<none>")), "RESULT-TYPE", result_type_gap)
    return result


def expect_tool_result(ctx, exchange, request_id, *, is_error, texts=None, stateless=True,
                       is_error_requirement="BRIDGE-RESPONSE"):
    """A tools/call result: text content, isError, and for 2026-07-28 the schema."""
    result = expect_result(ctx, exchange, request_id, stateless=stateless)
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
    if stateless:
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
                requirement="BRIDGE-PATH"):
    """The case's one REST request: method, raw path, query, and the body and headers given."""
    entries = ctx.backend()
    seen = [f"{e['method']} {e['raw_path']}" + (f"?{e['query']}" if e["query"] else "")
            for e in entries]
    want = f"{method} {raw_path}" + (f"?{query}" if query else "")
    ctx.check(f"the REST backend got {want}", seen == [want], [want], seen, requirement)
    if not entries:
        return None
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
    return entry


def expect_no_rest(ctx, requirement):
    entries = ctx.backend()
    seen = [f"{e['method']} {e['raw_path']}" for e in entries]
    return ctx.check("the request did not reach the REST backend", not entries, "no REST request",
                     seen, requirement)


def rejected(ctx, exchange, request_id, *, status, code, requirement, echo_id=True,
             rest_requirement=None):
    """A request that Envoy answers with an error itself: status, code, id, no REST request."""
    expect_status(ctx, exchange, status, requirement)
    expect_error(ctx, exchange, code, requirement)
    if echo_id and request_id is not None:
        expect_echo_id(ctx, exchange, request_id)
    expect_no_rest(ctx, rest_requirement or requirement)


def note_filter_id(ctx, exchange, request_id):
    """On listener C, notes an MCP filter error that has no id although the request had one."""
    message = exchange.json
    if isinstance(message, dict) and message.get("id") != request_id:
        ctx.note(f"the error's id is {message.get('id')!r}, not the request's {request_id!r}: "
                 "an MCP filter answer, outside this suite's scope")


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


@case("tools-list.local", "tools-list", "2026-07-28 tools/list, answered by the bridge "
      "(tool_list_local)", ("B",))
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


@case("tools-list.http-rule", "tools-list", "2026-07-28 tools/list, transcoded to the REST "
      "backend's GET /v1/tools (tool_list_http_rule)", ("C",))
def tools_list_http_rule(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id), headers("tools/list"))
    result = expect_result(ctx, exchange, request_id, result_type_gap="G2")
    ctx.check("the REST backend's tools", result.get("tools") == rest_server.TOOLS,
              quote(TOOL_NAMES), quote(result.get("tools")), "BRIDGE-HTTP-LIST")
    expect_cache_hints(ctx, result, gap="G2")
    ctx.schema("tools/list", result, gap="G2")
    expect_rest(ctx, "GET", "/v1/tools", body="", requirement="BRIDGE-HTTP-LIST")


@case("tools-list.legacy", "tools-list", "legacy tools/list (2025-11-25, no params._meta)",
      ("B", "C"))
def tools_list_legacy(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(legacy("tools/list", request_id), headers(version=LEGACY_PV))
    result = expect_result(ctx, exchange, request_id, stateless=False)
    requirement = "BRIDGE-LOCAL-LIST" if ctx.listener == "B" else "BRIDGE-HTTP-LIST"
    ctx.check("the tools", result.get("tools") == rest_server.TOOLS, quote(TOOL_NAMES),
              quote(result.get("tools")), requirement)


@case("tools-list.order", "tools-list", "tools/list twice: the same order", ("B", "C"))
def tools_list_order(ctx):
    names = []
    for _ in range(2):
        exchange = ctx.post(modern("tools/list", ctx.next_id()), headers("tools/list"))
        names.append([t.get("name") for t in (result_of(exchange) or {}).get("tools", [])])
    ctx.check("both lists have the same tools in the same order", names[0] == names[1] != [],
              quote(names[0]), quote(names[1]), "TOOLS-ORDER")


@case("tools-list.invalid-cursor", "tools-list", "tools/list with a cursor that the server never "
      "issued", ("B",))
def tools_list_invalid_cursor(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id, {"cursor": "no-such-cursor"}),
                        headers("tools/list"))
    expect_error(ctx, exchange, -32602, "PAGE-CURSOR", gap="G14")


# The MCP Python SDK.


@case("sdk.list-tools", "sdk", "the MCP Python SDK lists the tools", ("B", "C"))
def sdk_list_tools(ctx):

    async def run():
        async with ctx.sdk() as client:
            return [tool.name for tool in (await client.list_tools()).tools]

    names, error = ctx.run_sdk(run)
    ctx.check("list_tools() returns the tools", error is None and names == TOOL_NAMES,
              quote(TOOL_NAMES), sdk_outcome(names, error), "SDK-LIST",
              "G2" if ctx.listener == "C" else None)


@case("sdk.call-tool", "sdk", "the MCP Python SDK calls get_weather (call_tool also lists the "
      "tools, to validate the result, when it has not listed them)", ("B", "C"))
def sdk_call_tool(ctx):

    async def run():
        async with ctx.sdk() as client:
            result = await client.call_tool("get_weather", {"city": "Paris"})
            return result.is_error, [block.text for block in result.content]

    value, error = ctx.run_sdk(run)
    want = (False, [rest_answer("GET", "/v1/weather/Paris")])
    ctx.check("call_tool() returns the REST answer", error is None and value == want, quote(want),
              sdk_outcome(value, error), "SDK-CALL", "G2" if ctx.listener == "C" else None)
    entries = [e for e in ctx.backend() if e["raw_path"] == "/v1/weather/Paris"]
    ctx.check("the tools/call itself reached the REST backend", len(entries) == 1,
              "GET /v1/weather/Paris", [e["raw_path"] for e in ctx.backend()], "BRIDGE-PATH")


@case("sdk.call-tool-direct", "sdk", "the SDK's session sends tools/call without listing the "
      "tools first, and parses the result", ("B", "C"))
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


@case("sdk.mcp-param", "sdk", "the MCP Python SDK lists the tools, then calls get_forecast, with "
      "the Mcp-Param headers of its x-mcp-header annotations", ("B", "C"))
def sdk_mcp_param(ctx):

    async def run():
        async with ctx.sdk() as client:
            await client.list_tools()
            result = await client.call_tool("get_forecast", {"city": "São Paulo", "days": 3})
            return result.is_error

    is_error, error = ctx.run_sdk(run)
    ctx.check("list_tools() then call_tool() succeed", error is None and is_error is False,
              "isError false", sdk_outcome(is_error, error), "SDK-PARAM",
              "G2" if ctx.listener == "C" else None)


@case("sdk.mcp-param-encoding", "sdk", "tools/call with the Mcp-Param headers that the SDK's own "
      "encoder makes from get_forecast's input schema", ("B", "C"))
def sdk_mcp_param_encoding(ctx):
    arguments = {"city": "São Paulo", "days": 3, "detailed": True}
    params = mcp_param_headers(x_mcp_header_map(tool_schema("get_forecast")), arguments)
    ctx.check("the SDK Base64-encodes the non-ASCII city",
              params.get("Mcp-Param-City", "").startswith("=?base64?"), "=?base64?...?=",
              params.get("Mcp-Param-City"), "SDK-PARAM")
    exchange, request_id = call(ctx, "get_forecast", arguments, extra=list(params.items()))
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    expect_rest(ctx, "GET", "/v1/forecast/S%C3%A3o%20Paulo", "days=3&detailed=true",
                request_headers={
                    name: value for name, value in params.items()
                }, requirement="PARAM-FORWARD")


@case("sdk.discover", "sdk", "the SDK's send_discover gets a DiscoverResult that its model "
      "accepts", ("B", "C"))
def sdk_discover(ctx):

    async def run():
        async with ctx.sdk() as client:
            raw = await client.session.send_discover(PV)
            return mcp.types.DiscoverResult.model_validate(raw).supported_versions

    versions, error = ctx.run_sdk(run)
    ctx.check("the result parses, and supports 2026-07-28", error is None and PV in versions,
              PV, sdk_outcome(versions, error), "SDK-DISCOVER")


@case("sdk.auto-mode", "sdk", "Client(mode=\"auto\") negotiates 2026-07-28 with server/discover, "
      "and never sends initialize", ("B", "C"))
def sdk_auto_mode(ctx):

    async def run():
        async with ctx.sdk(mode="auto") as client:
            return client.protocol_version

    version, error = ctx.run_sdk(run)
    ctx.check("the client negotiates 2026-07-28", error is None and version == PV, PV,
              sdk_outcome(version, error), "SDK-DISCOVER")
    # Wait for a second entry too: a request after server/discover may be logged later.
    methods = [entry.get("mcp_method") for entry in ctx.access(2, timeout=1.0)]
    ctx.check("its only request is server/discover", methods == ["server/discover"],
              ["server/discover"], methods, "SDK-DISCOVER")


@case("sdk.unknown-tool", "sdk", "the SDK surfaces tools/call of an unknown tool as MCPError "
      "-32602", ("B", "C"))
def sdk_unknown_tool(ctx):

    async def run():
        async with ctx.sdk() as client:
            await client.call_tool("no_such_tool", {})

    _, error = ctx.run_sdk(run)
    ok = isinstance(error, MCPError) and error.code == -32602
    ctx.check("call_tool() raises MCPError -32602", ok, "MCPError -32602", sdk_outcome(None, error),
              "SDK-ERROR")


@case("sdk.tool-error", "sdk", "the SDK returns a REST 500 as a result with isError, not an "
      "exception", ("B", "C"))
def sdk_tool_error(ctx):

    async def run():
        async with ctx.sdk() as client:
            result = await client.call_tool("get_status", {"code": 500})
            return result.is_error, [block.text for block in result.content]

    value, error = ctx.run_sdk(run)
    want = (True, [rest_answer("GET", "/v1/status/500")])
    ctx.check("call_tool() returns isError true, with the REST answer",
              error is None and value == want, quote(want), sdk_outcome(value, error), "SDK-CALL")


@case("sdk.unauthorized", "sdk", "the SDK surfaces the REST backend's 401 as an error",
      ("C",))
def sdk_unauthorized(ctx):

    async def run():
        async with ctx.sdk() as client:
            await client.call_tool("get_account", {})

    _, error = ctx.run_sdk(run)
    ctx.check("call_tool() raises MCPError", isinstance(error, MCPError), "MCPError",
              sdk_outcome(None, error), "SDK-ERROR")


# Protocol versions.


@case("versioning.unsupported", "versioning", "a 2026-07-28 request at version 1900-01-01",
      ("B", "C"))
def versioning_unsupported(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id, meta_value=meta("1900-01-01")),
                        headers("tools/list", version="1900-01-01"))
    rejected(ctx, exchange, request_id, status=400, code=-32022,
             requirement="HTTP-UNSUPPORTED-VERSION", echo_id=ctx.listener == "B")
    data = (error_of(exchange) or {}).get("data") or {}
    ctx.check("data lists the supported versions, 2026-07-28 included, and the requested one",
              PV in (data.get("supported") or []) and data.get("requested") == "1900-01-01",
              f"supported with {PV}, requested 1900-01-01", data, "HTTP-UNSUPPORTED-VERSION")
    if ctx.listener == "C":
        note_filter_id(ctx, exchange, request_id)


@case("versioning.legacy-version-in-meta", "versioning", "a request with params._meta at the "
      "legacy version 2025-11-25", ("B", "C"))
def versioning_legacy_in_meta(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id, meta_value=meta(LEGACY_PV)),
                        headers("tools/list", version=LEGACY_PV))
    rejected(ctx, exchange, request_id, status=400, code=-32022,
             requirement="HTTP-UNSUPPORTED-VERSION")
    data = (error_of(exchange) or {}).get("data") or {}
    ctx.check("data lists 2026-07-28, and the requested version",
              PV in (data.get("supported") or []) and data.get("requested") == LEGACY_PV,
              f"supported with {PV}, requested {LEGACY_PV}", data, "HTTP-UNSUPPORTED-VERSION")


@case("versioning.legacy-unsupported-header", "versioning", "a legacy request (no params._meta) "
      "with MCP-Protocol-Version 1999-01-01", ("B", "C"))
def versioning_legacy_unsupported_header(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(legacy("tools/list", request_id), headers(version="1999-01-01"))
    expect_status(ctx, exchange, 400, "LEGACY-VERSION-400",
                  gap="G6" if ctx.listener == "B" else None)
    expect_no_rest(ctx, "LEGACY-VERSION-400")


@case("versioning.header-without-meta-version", "versioning", "MCP-Protocol-Version 2026-07-28 "
      "on a request whose params._meta has no protocol version", ("B", "C"))
def versioning_header_without_meta_version(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id, meta_value=meta(None)),
                        headers("tools/list"))
    expect_status(ctx, exchange, 400, "META-REQUIRED")
    expect_error(ctx, exchange, (-32602, -32020), "META-REQUIRED")
    expect_no_rest(ctx, "META-REQUIRED")


@case("versioning.legacy-no-header", "versioning", "a legacy request without MCP-Protocol-Version",
      ("B",))
def versioning_legacy_no_header(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(legacy("tools/list", request_id), headers(version=None))
    result = expect_result(ctx, exchange, request_id, stateless=False)
    ctx.check("served, as 2025-03-26", isinstance(result.get("tools"), list), "the tools",
              exchange.summary(), "LEGACY-DEFAULT")


@case("versioning.legacy-call", "versioning", "a legacy tools/call at 2025-06-18", ("B", "C"))
def versioning_legacy_call(ctx):
    exchange, request_id = legacy_call(ctx, "get_weather", {"city": "Paris"}, version="2025-06-18")
    expect_tool_result(ctx, exchange, request_id, is_error=False, stateless=False,
                       texts=[rest_answer("GET", "/v1/weather/Paris")])
    expect_rest(ctx, "GET", "/v1/weather/Paris")


# The stateless lifecycle.


@case("lifecycle.discover", "lifecycle", "server/discover", ("B", "C"))
def lifecycle_discover(ctx):
    request_id = "discover-1"
    exchange = ctx.post(modern("server/discover", request_id), headers("server/discover"))
    result = expect_result(ctx, exchange, request_id)
    ctx.check("supportedVersions has 2026-07-28", PV in (result.get("supportedVersions") or []),
              PV, result.get("supportedVersions"), "VER-DISCOVER")
    ctx.check("capabilities has tools", isinstance((result.get("capabilities") or {}).get("tools"),
                                                   dict), "an object", result.get("capabilities"),
              "TOOLS-CAPABILITY")
    expect_cache_hints(ctx, result)
    ctx.check("ttlMs and cacheScope are the configured 60000 and private",
              (result.get("ttlMs"), result.get("cacheScope")) == (60000, "private"),
              "60000, private", (result.get("ttlMs"), result.get("cacheScope")),
              "BRIDGE-DISCOVER-CACHE")
    ctx.schema("server/discover", result)
    expect_server_info(ctx, result)
    expect_no_rest(ctx, "VER-DISCOVER")


@case("lifecycle.discover-legacy", "lifecycle", "legacy server/discover (no params._meta), which "
      "legacy versions do not have", ("B",))
def lifecycle_discover_legacy(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(legacy("server/discover", request_id, {}), headers(version=LEGACY_PV))
    expect_error(ctx, exchange, -32601, "VER-MODERN")
    expect_echo_id(ctx, exchange, request_id)


@case("lifecycle.initialize", "lifecycle", "initialize with 2026-07-28 params._meta",
      ("B", "C"))
def lifecycle_initialize(ctx):
    request_id = ctx.next_id()
    params = {"protocolVersion": PV, "capabilities": {}, "clientInfo": CLIENT_INFO}
    exchange = ctx.post(modern("initialize", request_id, params), headers("initialize"))
    rejected(ctx, exchange, request_id, status=404, code=-32601, requirement="VER-MODERN")


@case("lifecycle.initialized", "lifecycle", "notifications/initialized with 2026-07-28 "
      "params._meta", ("B", "C"))
def lifecycle_initialized(ctx):
    exchange = ctx.post(modern("notifications/initialized", NO_ID),
                        headers("notifications/initialized"))
    ok = exchange.status is not None and 400 <= exchange.status < 500
    ctx.check("an HTTP error status (4xx): 2026-07-28 has no notifications/initialized", ok,
              "4xx", exchange.summary(), "VER-MODERN")
    ctx.check("no JSON-RPC result", result_of(exchange) is None, "no result", exchange.summary(),
              "HTTP-NOTIFICATION")
    if exchange.json is not None:
        expect_no_id(ctx, exchange, gap="G8")
    expect_no_rest(ctx, "VER-MODERN")


@case("lifecycle.ping", "lifecycle", "ping, which 2026-07-28 removed", ("B",))
def lifecycle_ping(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("ping", request_id), headers("ping"))
    rejected(ctx, exchange, request_id, status=404, code=-32601,
             requirement="HTTP-METHOD-NOT-FOUND")


@case("lifecycle.unsupported-method", "lifecycle", "resources/list, which this server does not "
      "have", ("B", "C"))
def lifecycle_unsupported_method(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("resources/list", request_id), headers("resources/list"))
    rejected(ctx, exchange, request_id, status=404, code=-32601,
             requirement="HTTP-METHOD-NOT-FOUND")


@case("lifecycle.legacy-initialize", "lifecycle", "initialize, legacy (2025-11-25)", ("B", "C"))
def lifecycle_legacy_initialize(ctx):
    request_id = ctx.next_id()
    params = {"protocolVersion": LEGACY_PV, "capabilities": {}, "clientInfo": CLIENT_INFO}
    # No MCP-Protocol-Version: a legacy client sends it only after initialize.
    exchange = ctx.post(legacy("initialize", request_id, params), headers(version=None))
    result = expect_result(ctx, exchange, request_id, stateless=False)
    info = result.get("serverInfo") or {}
    ok = (result.get("protocolVersion") == LEGACY_PV and
          isinstance((result.get("capabilities") or {}).get("tools"), dict) and
          isinstance(info.get("name"), str) and isinstance(info.get("version"), str))
    ctx.check("protocolVersion 2025-11-25, the tools capability, and serverInfo", ok,
              "2025-11-25, tools, serverInfo", quote(result), "LEGACY-INITIALIZE")


@case("lifecycle.legacy-initialize-newer", "lifecycle", "legacy initialize that asks for "
      "2026-07-28", ("B",))
def lifecycle_legacy_initialize_newer(ctx):
    request_id = ctx.next_id()
    params = {"protocolVersion": PV, "capabilities": {}, "clientInfo": CLIENT_INFO}
    exchange = ctx.post(legacy("initialize", request_id, params), headers(version=None))
    result = expect_result(ctx, exchange, request_id, stateless=False)
    ctx.check("protocolVersion is a legacy version that the server supports",
              result.get("protocolVersion") in LEGACY_VERSIONS, LEGACY_VERSIONS,
              result.get("protocolVersion"), "LEGACY-INITIALIZE")


@case("lifecycle.legacy-initialized", "lifecycle", "notifications/initialized, legacy",
      ("B", "C"))
def lifecycle_legacy_initialized(ctx):
    exchange = ctx.post(legacy("notifications/initialized", NO_ID), headers(version=LEGACY_PV))
    expect_status(ctx, exchange, 202, "LEGACY-INITIALIZED")
    ctx.check("no body", exchange.response_body == b"", "no body", exchange.summary(),
              "LEGACY-INITIALIZED")


@case("lifecycle.no-handshake", "lifecycle", "tools/call with no discover or initialize before "
      "it", ("B", "C"))
def lifecycle_no_handshake(ctx):
    exchange, request_id = call(ctx, "get_weather", {"city": "Paris"})
    result = expect_result(ctx, exchange, request_id)
    ctx.check("served", result.get("isError") is False, "isError false", exchange.summary(),
              "STATELESS")


@case("lifecycle.session-id", "lifecycle", "tools/call with an Mcp-Session-Id header", ("B", "C"))
def lifecycle_session_id(ctx):
    exchange, request_id = call(ctx, "get_weather", {"city": "Paris"},
                                extra=[("Mcp-Session-Id", "e2e-session")])
    result = expect_result(ctx, exchange, request_id)
    ctx.check("served", result.get("isError") is False, "isError false", exchange.summary(),
              "HTTP-SESSION")
    ctx.check("no Mcp-Session-Id in the response", exchange.header("mcp-session-id") is None,
              "none", exchange.header("mcp-session-id"), "HTTP-SESSION")


@case("lifecycle.get", "lifecycle", "GET on the MCP endpoint", ("B", "C"))
def lifecycle_get(ctx):
    exchange = ctx.post(method="GET", headers=[("Accept", "text/event-stream"),
                                               ("MCP-Protocol-Version", PV)], timeout=3)
    expect_status(ctx, exchange, 405, "HTTP-405")
    ctx.check("Allow: POST", exchange.header("allow") == "POST", "POST", exchange.header("allow"),
              "HTTP-405")
    ctx.check("a complete response", exchange.status is not None and exchange.error is None,
              "the whole response", exchange.summary(), "HTTP-FRAMING")


@case("lifecycle.delete", "lifecycle", "DELETE on the MCP endpoint", ("B", "C"))
def lifecycle_delete(ctx):
    exchange = ctx.post(method="DELETE", headers=[("MCP-Protocol-Version", PV),
                                                  ("Mcp-Session-Id", "e2e-session")], timeout=3)
    expect_status(ctx, exchange, 405, "HTTP-405")
    ctx.check("a complete response", exchange.status is not None and exchange.error is None,
              "the whole response", exchange.summary(), "HTTP-FRAMING")


# The standard MCP headers. On listener C, the MCP filter checks them before the bridge.


def header_case(ctx, header_list, tool="get_weather", arguments=None, echo_id=None,
                requirement="HTTP-STANDARD-HEADERS"):
    request_id = ctx.next_id()
    body = modern("tools/call", request_id, {"name": tool, "arguments": arguments or {
        "city": "Paris"
    }})
    exchange = ctx.post(body, header_list)
    echo = ctx.listener == "B" if echo_id is None else echo_id
    rejected(ctx, exchange, request_id, status=400, code=-32020, requirement=requirement,
             echo_id=echo)
    if ctx.listener == "C":
        note_filter_id(ctx, exchange, request_id)
    return exchange


def drop(header_list, name):
    return [(n, v) for n, v in header_list if n.lower() != name.lower()]


@case("headers.version-missing", "headers", "tools/call without MCP-Protocol-Version", ("B", "C"))
def headers_version_missing(ctx):
    header_case(ctx, drop(headers("tools/call", "get_weather"), "MCP-Protocol-Version"),
                requirement="HTTP-VERSION-HEADER")


@case("headers.version-mismatch", "headers", "MCP-Protocol-Version 2025-11-25 on a 2026-07-28 "
      "body", ("B", "C"))
def headers_version_mismatch(ctx):
    header_case(ctx, headers("tools/call", "get_weather", version=LEGACY_PV),
                requirement="HTTP-VERSION-HEADER")


@case("headers.version-duplicate", "headers", "MCP-Protocol-Version twice", ("B", "C"))
def headers_version_duplicate(ctx):
    header_case(ctx, headers("tools/call", "get_weather", extra=[("MCP-Protocol-Version", PV)]),
                requirement="HTTP-VERSION-HEADER")


@case("headers.method-missing", "headers", "tools/call without Mcp-Method", ("B", "C"))
def headers_method_missing(ctx):
    header_case(ctx, drop(headers("tools/call", "get_weather"), "Mcp-Method"))


@case("headers.method-mismatch", "headers", "Mcp-Method tools/list on a tools/call", ("B", "C"))
def headers_method_mismatch(ctx):
    header_case(ctx, headers("tools/list", "get_weather"))


@case("headers.method-case", "headers", "Mcp-Method TOOLS/CALL: header values are "
      "case-sensitive", ("B", "C"))
def headers_method_case(ctx):
    header_case(ctx, headers("TOOLS/CALL", "get_weather"))


@case("headers.method-duplicate", "headers", "Mcp-Method twice", ("B", "C"))
def headers_method_duplicate(ctx):
    header_case(ctx, headers("tools/call", "get_weather", extra=[("Mcp-Method", "tools/call")]))


@case("headers.name-missing", "headers", "tools/call without Mcp-Name", ("B", "C"))
def headers_name_missing(ctx):
    header_case(ctx, headers("tools/call"))


@case("headers.name-mismatch", "headers", "Mcp-Name get_forecast on a tools/call of get_weather",
      ("B", "C"))
def headers_name_mismatch(ctx):
    header_case(ctx, headers("tools/call", "get_forecast"))


@case("headers.name-duplicate", "headers", "Mcp-Name twice", ("B", "C"))
def headers_name_duplicate(ctx):
    header_case(ctx, headers("tools/call", "get_weather", extra=[("Mcp-Name", "get_weather")]))


@case("headers.name-invalid-base64", "headers", "Mcp-Name =?base64?%%%?=, which does not decode",
      ("B", "C"))
def headers_name_invalid_base64(ctx):
    header_case(ctx, headers("tools/call", "=?base64?%%%?="))


@case("headers.name-base64", "headers", "Mcp-Name get_weather, Base64-encoded", ("B", "C"))
def headers_name_base64(ctx):
    encoded = f"=?base64?{base64.b64encode(b'get_weather').decode()}?="
    exchange, request_id = call(ctx, "get_weather", {"city": "Paris"}, name=encoded)
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       is_error_requirement="HTTP-BASE64")
    expect_rest(ctx, "GET", "/v1/weather/Paris", requirement="HTTP-BASE64")


@case("headers.name-case", "headers", "the MCP headers' names in lowercase and uppercase",
      ("B", "C"))
def headers_name_case(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(
        modern("tools/call", request_id, {"name": "get_weather", "arguments": {"city": "Paris"}}),
        [("content-type", "application/json"), ("accept", "application/json, text/event-stream"),
         ("mcp-protocol-version", PV), ("MCP-METHOD", "tools/call"), ("mcp-name", "get_weather")])
    expect_tool_result(ctx, exchange, request_id, is_error=False, is_error_requirement="HTTP-CASE")


@case("headers.error-before-not-found", "headers", "resources/list with a wrong Mcp-Method: the "
      "header error, not 404", ("B", "C"))
def headers_error_before_not_found(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("resources/list", request_id), headers("tools/list"))
    rejected(ctx, exchange, request_id, status=400, code=-32020, requirement="BRIDGE-HEADER-FIRST",
             echo_id=ctx.listener == "B")


# Mcp-Param headers: get_forecast's City (string), Days (integer) and Detailed (boolean).

FORECAST = {"city": "Paris", "days": 3, "detailed": True}
FORECAST_HEADERS = [("Mcp-Param-City", "Paris"), ("Mcp-Param-Days", "3"),
                    ("Mcp-Param-Detailed", "true")]


def param_call(ctx, arguments, param_headers):
    return call(ctx, "get_forecast", arguments, extra=param_headers)


def param_rejected(ctx, arguments, param_headers, requirement="PARAM-MATCH"):
    exchange, request_id = param_call(ctx, arguments, param_headers)
    rejected(ctx, exchange, request_id, status=400, code=-32020, requirement=requirement)


def param_accepted(ctx, arguments, param_headers, requirement, raw_path="/v1/forecast/Paris",
                   query=None):
    exchange, request_id = param_call(ctx, arguments, param_headers)
    expect_tool_result(ctx, exchange, request_id, is_error=False, is_error_requirement=requirement)
    if query is not None:
        expect_rest(ctx, "GET", raw_path, query, requirement=requirement)


@case("params.valid", "params", "get_forecast with matching Mcp-Param headers", ("B", "C"))
def params_valid(ctx):
    exchange, request_id = param_call(ctx, FORECAST, FORECAST_HEADERS)
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       is_error_requirement="PARAM-MATCH")
    expect_rest(ctx, "GET", "/v1/forecast/Paris", "days=3&detailed=true",
                request_headers=dict(FORECAST_HEADERS), requirement="PARAM-FORWARD")


@case("params.missing", "params", "a present argument without its Mcp-Param header", ("B", "C"))
def params_missing(ctx):
    param_rejected(ctx, FORECAST, drop(FORECAST_HEADERS, "Mcp-Param-City"))


@case("params.mismatch", "params", "Mcp-Param-City Lyon for city Paris", ("C",))
def params_mismatch(ctx):
    param_rejected(ctx, FORECAST, [("Mcp-Param-City", "Lyon"), *FORECAST_HEADERS[1:]])


@case("params.value-case", "params", "Mcp-Param-City paris for city Paris: values are "
      "case-sensitive", ("C",))
def params_value_case(ctx):
    param_rejected(ctx, FORECAST, [("Mcp-Param-City", "paris"), *FORECAST_HEADERS[1:]])


@case("params.unexpected", "params", "Mcp-Param-Days without a days argument", ("C",))
def params_unexpected(ctx):
    param_rejected(ctx, {"city": "Paris"}, [("Mcp-Param-City", "Paris"), ("Mcp-Param-Days", "3")],
                   requirement="PARAM-UNEXPECTED")


@case("params.null", "params", "days null, and no Mcp-Param-Days", ("C",))
def params_null(ctx):
    param_accepted(ctx, {"city": "Paris", "days": None}, [("Mcp-Param-City", "Paris")],
                   "PARAM-ABSENT")


@case("params.absent", "params", "no days argument, and no Mcp-Param-Days", ("C",))
def params_absent(ctx):
    param_accepted(ctx, {"city": "Paris"}, [("Mcp-Param-City", "Paris")], "PARAM-ABSENT",
                   query="")


@case("params.duplicate", "params", "Mcp-Param-City twice", ("C",))
def params_duplicate(ctx):
    param_rejected(ctx, FORECAST, [*FORECAST_HEADERS, ("Mcp-Param-City", "Paris")],
                   requirement="PARAM-DUPLICATE")


@case("params.invalid-characters", "params", "Mcp-Param-City São Paulo, raw UTF-8", ("C",))
def params_invalid_characters(ctx):
    param_rejected(ctx, {"city": "São Paulo"}, [("Mcp-Param-City", "São Paulo".encode())])


@case("params.base64", "params", "Mcp-Param-City São Paulo, Base64-encoded", ("C",))
def params_base64(ctx):
    encoded = f"=?base64?{base64.b64encode('São Paulo'.encode()).decode()}?="
    param_accepted(ctx, {"city": "São Paulo"}, [("Mcp-Param-City", encoded)], "HTTP-BASE64",
                   raw_path="/v1/forecast/S%C3%A3o%20Paulo", query="")


@case("params.invalid-base64", "params", "Mcp-Param-City =?base64?%%%?=", ("C",))
def params_invalid_base64(ctx):
    param_rejected(ctx, {"city": "Paris"}, [("Mcp-Param-City", "=?base64?%%%?=")],
                   requirement="HTTP-BASE64")


@case("params.integer-numeric", "params", "Mcp-Param-Days 3.0 for days 3", ("C",))
def params_integer_numeric(ctx):
    param_accepted(ctx, FORECAST, [*FORECAST_HEADERS[:1], ("Mcp-Param-Days", "3.0"),
                                   FORECAST_HEADERS[2]], "PARAM-INTEGER")


@case("params.integer-mismatch", "params", "Mcp-Param-Days 4 for days 3", ("C",))
def params_integer_mismatch(ctx):
    param_rejected(ctx, FORECAST, [FORECAST_HEADERS[0], ("Mcp-Param-Days", "4"),
                                   FORECAST_HEADERS[2]])


@case("params.boolean-case", "params", "Mcp-Param-Detailed True: booleans are lowercase", ("C",))
def params_boolean_case(ctx):
    param_rejected(ctx, FORECAST, [*FORECAST_HEADERS[:2], ("Mcp-Param-Detailed", "True")])


@case("params.header-name-case", "params", "the Mcp-Param headers' names in lowercase", ("C",))
def params_header_name_case(ctx):
    param_accepted(ctx, FORECAST, [(n.lower(), v) for n, v in FORECAST_HEADERS], "HTTP-CASE")


@case("params.legacy", "params", "a legacy tools/call with a wrong Mcp-Param header: not "
      "validated", ("C",))
def params_legacy(ctx):
    exchange, request_id = legacy_call(ctx, "get_forecast", FORECAST,
                                       extra=[("Mcp-Param-City", "Lyon")])
    expect_tool_result(ctx, exchange, request_id, is_error=False, stateless=False,
                       is_error_requirement="PARAM-SCOPE")


# Transcoding of requests and responses.


@case("transcoding.get", "transcoding", "get_weather: path variable, and the other arguments as "
      "the query", ("B", "C"))
def transcoding_get(ctx):
    exchange, request_id = call(ctx, "get_weather", {"city": "Paris", "units": "imperial"})
    result = expect_tool_result(
        ctx, exchange, request_id, is_error=False,
        texts=[rest_answer("GET", "/v1/weather/Paris", "units=imperial")])
    expect_rest(ctx, "GET", "/v1/weather/Paris", "units=imperial", body="",
                requirement="BRIDGE-QUERY")
    expect_server_info(ctx, result, gap="G12")


@case("transcoding.path-encoding", "transcoding", "get_weather New York/NY: {city} fills one "
      "segment, its / encoded", ("C",))
def transcoding_path_encoding(ctx):
    exchange, request_id = call(ctx, "get_weather", {"city": "New York/NY"})
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    expect_rest(ctx, "GET", "/v1/weather/New%20York%2FNY")


@case("transcoding.path-pattern", "transcoding", "get_file: {name=projects/*/files/*} spans "
      "segments", ("C",))
def transcoding_path_pattern(ctx):
    exchange, request_id = call(ctx, "get_file", {"name": "projects/p1/files/f1"})
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       texts=[rest_answer("GET", "/v1/projects/p1/files/f1")])
    expect_rest(ctx, "GET", "/v1/projects/p1/files/f1")


@case("transcoding.query", "transcoding", "search_items: nested and repeated query parameters",
      ("C",))
def transcoding_query(ctx):
    arguments = {"q": "desk lamp", "filter": {"color": "red", "size": "L"}, "tags": ["a", "b"],
                 "limit": 5, "exact": True}
    exchange, request_id = call(ctx, "search_items", arguments)
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    expect_rest(ctx, "GET", "/v1/search",
                "exact=true&filter.color=red&filter.size=L&limit=5&q=desk%20lamp&tags=a&tags=b",
                requirement="BRIDGE-QUERY")


@case("transcoding.body-star", "transcoding", "create_order: body \"*\"", ("C",))
def transcoding_body_star(ctx):
    arguments = {"item": "widget", "quantity": 3, "options": {"gift": True}}
    exchange, request_id = call(ctx, "create_order", arguments)
    answer = rest_answer("POST", "/v1/orders", body=json.dumps(arguments).encode())
    expect_tool_result(ctx, exchange, request_id, is_error=False, texts=[answer])
    expect_rest(ctx, "POST", "/v1/orders", body=arguments, request_headers={
        "content-type": "application/json"
    }, requirement="BRIDGE-BODY")


@case("transcoding.body-field", "transcoding", "update_order: body \"order\", the rest in the "
      "query", ("C",))
def transcoding_body_field(ctx):
    exchange, request_id = call(ctx, "update_order",
                                {"order_id": "o-1", "order": {"quantity": 5}, "notify": True})
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    expect_rest(ctx, "PUT", "/v1/orders/o-1", "notify=true", body={"quantity": 5},
                requirement="BRIDGE-BODY")


@case("transcoding.patch", "transcoding", "patch_order: PATCH, body \"*\" without the path "
      "variable", ("C",))
def transcoding_patch(ctx):
    exchange, request_id = call(ctx, "patch_order", {"order_id": "o-1", "status": "shipped"})
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    expect_rest(ctx, "PATCH", "/v1/orders/o-1", body={"status": "shipped"},
                requirement="BRIDGE-BODY")


@case("transcoding.delete", "transcoding", "delete_order: DELETE, and the REST 204", ("C",))
def transcoding_delete(ctx):
    exchange, request_id = call(ctx, "delete_order", {"order_id": "o-1"})
    expect_tool_result(ctx, exchange, request_id, is_error=False, texts=[""])
    expect_rest(ctx, "DELETE", "/v1/orders/o-1", body="")


@case("transcoding.bindings", "transcoding", "get_account: a header and a cookie binding", ("C",))
def transcoding_bindings(ctx):
    exchange, request_id = call(ctx, "get_account",
                                {"api_key": "e2e-key", "session_id": "s-1", "verbose": True})
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    entry = expect_rest(ctx, "GET", "/v1/account", "verbose=true",
                        request_headers={"x-api-key": "e2e-key"}, requirement="BRIDGE-BINDINGS")
    cookie = (entry or {}).get("headers", {}).get("cookie", "")
    ctx.check("the REST request has the cookie session=s-1", "session=s-1" in cookie,
              "session=s-1", cookie, "BRIDGE-BINDINGS")


@case("transcoding.method-precedence", "transcoding", "probe_method, whose rule sets get and post",
      ("C",))
def transcoding_method_precedence(ctx):
    exchange, request_id = call(ctx, "probe_method", {})
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    methods = [entry["method"] for entry in ctx.backend()]
    ctx.check("the REST request is a POST", methods == ["POST"], ["POST"], methods,
              "BRIDGE-METHOD", gap="G11")


@case("transcoding.trace-context", "transcoding", "traceparent in params._meta", ("C",))
def transcoding_trace_context(ctx):
    traceparent = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    exchange, request_id = call(ctx, "get_weather", {"city": "Paris"},
                                meta_value=meta(traceparent=traceparent))
    expect_tool_result(ctx, exchange, request_id, is_error=False)
    expect_rest(ctx, "GET", "/v1/weather/Paris", request_headers={"traceparent": traceparent},
                requirement="BRIDGE-TRACE")


@case("transcoding.streaming", "transcoding", "stream_text: a chunked REST answer, streamed",
      ("C",))
def transcoding_streaming(ctx):
    exchange, request_id = call(ctx, "stream_text", {})
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       texts=[b"".join(rest_server.TEXT_CHUNKS).decode()],
                       is_error_requirement="BRIDGE-STREAMING")


@case("transcoding.streaming-events", "transcoding", "stream_events: each server-sent event is a "
      "text item", ("C",))
def transcoding_streaming_events(ctx):
    exchange, request_id = call(ctx, "stream_events", {})
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       texts=['{"event":1}', '{"event":2}'],
                       is_error_requirement="BRIDGE-STREAMING")


@case("transcoding.streaming-error", "transcoding", "stream_status 500: streamed, isError",
      ("C",))
def transcoding_streaming_error(ctx):
    exchange, request_id = call(ctx, "stream_status", {"code": 500})
    expect_tool_result(ctx, exchange, request_id, is_error=True,
                       texts=[rest_answer("GET", "/v1/status/500")],
                       is_error_requirement="BRIDGE-STREAMING")


@case("transcoding.streaming-no-body", "transcoding", "stream_status 204: a streamed REST answer "
      "with no body", ("C",))
def transcoding_streaming_no_body(ctx):
    exchange, request_id = call(ctx, "stream_status", {"code": 204})
    ok = result_of(exchange) is not None and (exchange.json or {}).get("id") == request_id
    ctx.check("a JSON-RPC response", ok, "a JSON-RPC result", exchange.summary(),
              "HTTP-JSON-RESPONSE")


# Errors: of the REST backend, of the tool's arguments, and of the request.


def register_rest_status(code):

    @case(f"errors.rest-{code}", "errors", f"get_status {code}: a tool execution error", ("C",))
    def errors_rest_status(ctx):
        exchange, request_id = call(ctx, "get_status", {"code": code})
        expect_tool_result(ctx, exchange, request_id, is_error=True,
                           texts=[rest_answer("GET", f"/v1/status/{code}")],
                           is_error_requirement="TOOLS-EXECUTION-ERROR")


for rest_status in (400, 404, 500, 503):
    register_rest_status(rest_status)


@case("errors.rest-no-body", "errors", "get_status 204", ("C",))
def errors_rest_no_body(ctx):
    exchange, request_id = call(ctx, "get_status", {"code": 204})
    expect_tool_result(ctx, exchange, request_id, is_error=False, texts=[""])


@case("errors.rest-401", "errors", "get_status 401: the status and WWW-Authenticate are kept",
      ("C",))
def errors_rest_401(ctx):
    exchange, request_id = call(ctx, "get_status", {"code": 401})
    expect_status(ctx, exchange, 401, "BRIDGE-RESPONSE")
    ctx.check("WWW-Authenticate from the REST backend", exchange.header("www-authenticate") ==
              'Bearer realm="e2e"', 'Bearer realm="e2e"', exchange.header("www-authenticate"),
              "BRIDGE-RESPONSE")
    ctx.check("a result with isError true", (result_of(exchange) or {}).get("isError") is True,
              "isError true", exchange.summary(), "BRIDGE-RESPONSE")
    expect_echo_id(ctx, exchange, request_id)


@case("errors.rest-403", "errors", "get_account with a wrong API key: 403 is kept", ("C",))
def errors_rest_403(ctx):
    exchange, request_id = call(ctx, "get_account", {"api_key": "wrong"})
    expect_status(ctx, exchange, 403, "BRIDGE-RESPONSE")
    ctx.check("WWW-Authenticate from the REST backend", "insufficient_scope" in
              (exchange.header("www-authenticate") or ""), 'Bearer error="insufficient_scope"',
              exchange.header("www-authenticate"), "BRIDGE-RESPONSE")
    expect_echo_id(ctx, exchange, request_id)


@case("errors.rest-not-utf8", "errors", "get_binary: a REST answer that is not UTF-8", ("C",))
def errors_rest_not_utf8(ctx):
    exchange, request_id = call(ctx, "get_binary", {})
    expect_tool_result(ctx, exchange, request_id, is_error=True,
                       is_error_requirement="TOOLS-EXECUTION-ERROR")


@case("errors.rest-too-large", "errors", "get_large: a REST answer over 1 MiB", ("C",))
def errors_rest_too_large(ctx):
    exchange, request_id = call(ctx, "get_large", {})
    expect_error(ctx, exchange, None, "BRIDGE-RESPONSE-LIMIT")
    expect_echo_id(ctx, exchange, request_id)
    expect_modern_code(ctx, exchange)


@case("errors.unknown-tool", "errors", "tools/call of an unknown tool", ("B", "C"))
def errors_unknown_tool(ctx):
    exchange, request_id = call(ctx, "no_such_tool", {})
    expect_error(ctx, exchange, -32602, "TOOLS-PROTOCOL-ERROR")
    expect_echo_id(ctx, exchange, request_id)
    expect_no_rest(ctx, "TOOLS-PROTOCOL-ERROR")


@case("errors.arguments-not-object", "errors", "tools/call whose arguments are a string", ("C",))
def errors_arguments_not_object(ctx):
    exchange, request_id = call(ctx, "get_weather", "Paris")
    expect_error(ctx, exchange, -32602, "TOOLS-PROTOCOL-ERROR")
    expect_echo_id(ctx, exchange, request_id)
    expect_no_rest(ctx, "TOOLS-PROTOCOL-ERROR")


def input_error(ctx, tool, arguments, requirement):
    """An invalid argument: not sent to the REST backend, and a tool execution error."""
    exchange, request_id = call(ctx, tool, arguments)
    expect_no_rest(ctx, requirement)
    result = result_of(exchange) or {}
    ctx.check("a result with isError true (a tool execution error)", result.get("isError") is True,
              "isError true", exchange.summary(), "TOOLS-EXECUTION-ERROR", gap="G10")
    expect_echo_id(ctx, exchange, request_id)


@case("errors.missing-argument", "errors", "get_weather without city, its path variable", ("C",))
def errors_missing_argument(ctx):
    input_error(ctx, "get_weather", {}, "BRIDGE-PATH")


@case("errors.missing-body-field", "errors", "update_order without order, its body", ("C",))
def errors_missing_body_field(ctx):
    input_error(ctx, "update_order", {"order_id": "o-1"}, "BRIDGE-BODY")


@case("errors.path-traversal", "errors", "get_weather with city ..", ("C",))
def errors_path_traversal(ctx):
    input_error(ctx, "get_weather", {"city": ".."}, "BRIDGE-TRAVERSAL")


@case("errors.invalid-header-value", "errors", "get_account with a CR LF in api_key, its header",
      ("C",))
def errors_invalid_header_value(ctx):
    input_error(ctx, "get_account", {"api_key": "e2e\r\nkey"}, "BRIDGE-BINDINGS")


@case("errors.invalid-cookie-value", "errors", "get_account with a space in session_id, its "
      "cookie", ("C",))
def errors_invalid_cookie_value(ctx):
    input_error(ctx, "get_account", {"api_key": "e2e-key", "session_id": "a b"}, "BRIDGE-BINDINGS")


@case("errors.parse-error", "errors", "a body that is not JSON", ("B",))
def errors_parse_error(ctx):
    exchange = ctx.post(raw=b"{not json", headers=headers("tools/list"))
    expect_error(ctx, exchange, -32700, "JSONRPC-PARSE")
    expect_no_id(ctx, exchange, gap="G8")


@case("errors.batch", "errors", "a batch: a JSON array of two requests", ("B",))
def errors_batch(ctx):
    batch = [modern("tools/list", ctx.next_id()), modern("tools/list", ctx.next_id())]
    exchange = ctx.post(batch, headers("tools/list"))
    expect_error(ctx, exchange, -32600, "JSONRPC-SINGLE")
    expect_no_id(ctx, exchange, gap="G8")


@case("errors.missing-method", "errors", "a request without method", ("B",))
def errors_missing_method(ctx):
    request_id = ctx.next_id()
    message = modern("tools/list", request_id)
    del message["method"]
    exchange = ctx.post(message, headers("tools/list"))
    expect_error(ctx, exchange, -32600, "JSONRPC-METHOD")
    expect_echo_id(ctx, exchange, request_id)


@case("errors.null-id", "errors", "a request whose id is null", ("B",))
def errors_null_id(ctx):
    exchange = ctx.post(modern("tools/list", None), headers("tools/list"))
    expect_error(ctx, exchange, -32600, "JSONRPC-ID")
    expect_no_id(ctx, exchange, gap="G8")


@case("errors.fractional-id", "errors", "a request whose id is 1.5", ("B",))
def errors_fractional_id(ctx):
    exchange = ctx.post(modern("tools/list", 1.5), headers("tools/list"))
    expect_error(ctx, exchange, -32600, "JSONRPC-ID")
    expect_no_id(ctx, exchange, gap="G8")


# jsonrpc missing or not "2.0". In the supported chain (listener C), the MCP filter rejects these
# requests before the bridge: regression checks. The bridge alone (listener B) does not check
# jsonrpc: diagnostic checks, which are not endpoint compliance failures (DIAGNOSTICS["G9"]).


@case("errors.jsonrpc-missing", "errors", "a request without jsonrpc, to the bridge alone "
      "(diagnostic: the MCP filter checks jsonrpc in the supported chain)", ("B",))
def errors_jsonrpc_missing(ctx):
    request_id = ctx.next_id()
    message = modern("tools/list", request_id)
    del message["jsonrpc"]
    exchange = ctx.post(message, headers("tools/list"))
    expect_error(ctx, exchange, -32600, "JSONRPC-VERSION", diagnostic="G9")


@case("errors.jsonrpc-version", "errors", "a request with jsonrpc 1.0, to the bridge alone "
      "(diagnostic: the MCP filter checks jsonrpc in the supported chain)", ("B",))
def errors_jsonrpc_version(ctx):
    request_id = ctx.next_id()
    message = modern("tools/list", request_id) | {"jsonrpc": "1.0"}
    exchange = ctx.post(message, headers("tools/list"))
    expect_error(ctx, exchange, -32600, "JSONRPC-VERSION", diagnostic="G9")


def jsonrpc_rejected_by_mcp_filter(ctx, jsonrpc):
    """An otherwise valid 2026-07-28 tools/call, with jsonrpc removed (None) or set to jsonrpc: the
    MCP filter must reject it with 400, before the bridge and the REST backend."""
    request_id = ctx.next_id()
    message = modern("tools/call", request_id,
                     {"name": "get_weather", "arguments": {"city": "Paris"}})
    if jsonrpc is None:
        del message["jsonrpc"]
    else:
        message["jsonrpc"] = jsonrpc
    exchange = ctx.post(message, headers("tools/call", "get_weather"))
    expect_status(ctx, exchange, 400, "MCP-FILTER-JSONRPC")
    expect_no_rest(ctx, "MCP-FILTER-JSONRPC")
    entries = ctx.access(1)
    details = [entry.get("response_code_details") for entry in entries]
    bridge = [entry.get("bridge") for entry in entries]
    ctx.check("rejected by the MCP filter, before the bridge (access log: mcp_not_jsonrpc, no "
              "bridge metadata)", details == ["mcp_not_jsonrpc"] and bridge == [None],
              "mcp_not_jsonrpc, no bridge metadata", f"{details}, bridge metadata {bridge}",
              "MCP-FILTER-JSONRPC")
    if error_of(exchange) is None:
        ctx.note(f"the MCP filter's 400 is {exchange.header('content-type') or 'no content-type'}, "
                 f"{exchange.text!r}: not a JSON-RPC error (-32600)")


@case("errors.jsonrpc-missing", "errors", "a tools/call without jsonrpc, through the MCP filter: "
      "rejected before the bridge", ("C",))
def errors_jsonrpc_missing_chain(ctx):
    jsonrpc_rejected_by_mcp_filter(ctx, None)


@case("errors.jsonrpc-version", "errors", "a tools/call with jsonrpc 1.0, through the MCP filter: "
      "rejected before the bridge", ("C",))
def errors_jsonrpc_version_chain(ctx):
    jsonrpc_rejected_by_mcp_filter(ctx, "1.0")


@case("errors.notification", "errors", "tools/list without an id: a notification, with "
      "2026-07-28 params._meta", ("B",))
def errors_notification(ctx):
    exchange = ctx.post(modern("tools/list", NO_ID), headers("tools/list"))
    ok = exchange.status == 202 or (exchange.status is not None and 400 <= exchange.status < 600)
    ctx.check("202, or an HTTP error status", ok, "202 or 4xx/5xx", exchange.summary(),
              "HTTP-NOTIFICATION", gap="G7")


@case("errors.notification-legacy", "errors", "notifications/cancelled, legacy", ("B",))
def errors_notification_legacy(ctx):
    exchange = ctx.post(legacy("notifications/cancelled", NO_ID, {"requestId": 1}),
                        headers(version=LEGACY_PV))
    ok = exchange.status == 202 or (exchange.status is not None and 400 <= exchange.status < 600)
    ctx.check("202, or an HTTP error status", ok, "202 or 4xx/5xx", exchange.summary(),
              "HTTP-NOTIFICATION", gap="G7")


@case("errors.body-too-large", "errors", "a tools/call body over 64 KiB", ("B",))
def errors_body_too_large(ctx):
    exchange, _ = call(ctx, "create_order", {"item": "x" * 70000, "quantity": 1})
    expect_status(ctx, exchange, 413, "BRIDGE-REQUEST-LIMIT")
    expect_error(ctx, exchange, None, "BRIDGE-REQUEST-LIMIT")
    expect_no_id(ctx, exchange, gap="G8")
    expect_modern_code(ctx, exchange)
    expect_no_rest(ctx, "BRIDGE-REQUEST-LIMIT")


@case("errors.large-body", "errors", "a tools/call body of 20 KiB, under the 64 KiB limit",
      ("B", "C"))
def errors_large_body(ctx):
    arguments = {"item": "x" * 20000, "quantity": 1}
    exchange, request_id = call(ctx, "create_order", arguments)
    expect_tool_result(ctx, exchange, request_id, is_error=False,
                       is_error_requirement="BRIDGE-REQUEST-LIMIT")


@case("errors.empty-body", "errors", "a POST with an empty body", ("B", "C"))
def errors_empty_body(ctx):
    exchange = ctx.post(raw=b"", headers=headers("tools/list"), timeout=5)
    ctx.check("an error response", exchange.status is not None and exchange.status >= 400,
              "an HTTP error status", exchange.summary(), "HTTP-ANSWERED")


# Client capabilities, which every 2026-07-28 request must have.


@case("capabilities.missing", "capabilities", "2026-07-28 tools/list without client capabilities "
      "in params._meta", ("B", "C"))
def capabilities_missing(ctx):
    request_id = ctx.next_id()
    exchange = ctx.post(modern("tools/list", request_id, meta_value=meta(capabilities=False)),
                        headers("tools/list"))
    rejected(ctx, exchange, request_id, status=400, code=-32602, requirement="META-REQUIRED",
             rest_requirement="BRIDGE-MCP-FILTER" if ctx.listener == "C" else "META-REQUIRED")
