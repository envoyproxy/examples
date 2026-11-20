"""The MCP client, and the checks, of the MCP filter end-to-end test.

Exercises MCP protocol version 2026-07-28 through Envoy's MCP filter, with mcp_server.py behind it:

- With the official MCP Python SDK (the `mcp` package, at version 2.2.0, which the suite pins),
  pinned to protocol version 2026-07-28: stateless tools/list and tools/call through the main
  listener, which must reach the server and return its results; and tools/list through the capped
  listener, whose MCP filter supports protocol versions up to 2025-11-25 only, so that it must
  answer -32022 itself.
- With raw HTTP, for requests that the SDK does not send: requests that each break one 2026-07-28
  rule, which the MCP filter must answer itself, without forwarding them; a valid tools/call whose
  Mcp-Name header is base64-encoded, which must reach the server; and the legacy handshake
  methods, initialize and notifications/initialized, which the MCP filter forwards, so that the
  server, not Envoy, answers them. The answers that their checks expect are the pinned SDK's, not
  protocol requirements.

For each case, it checks the response, Envoy's access log, the MCP filter's counters, and whether
the request reached the server, in the server's request log. docker/client_entrypoint.py runs it
once the server and Envoy are ready. See README.md.
"""
import argparse
import base64
import dataclasses
import functools
import http.client
import importlib.metadata
import json
import pathlib
import socket
import sys
import time
import urllib.request

import anyio
from mcp import Client, MCPError
from mcp.shared.inbound import MCP_METHOD_HEADER, MCP_NAME_HEADER, MCP_PROTOCOL_VERSION_HEADER
from mcp.types import (CLIENT_CAPABILITIES_META_KEY, CLIENT_INFO_META_KEY, HEADER_MISMATCH,
                       INVALID_PARAMS, METHOD_NOT_FOUND, PROTOCOL_VERSION_META_KEY,
                       UNSUPPORTED_PROTOCOL_VERSION, Implementation, TextContent)

# The protocol version under test.
PROTOCOL_VERSION = "2026-07-28"
# The protocol versions the MCP filter knows: kKnownProtocolVersions in
# source/extensions/filters/http/mcp/mcp_filter.cc.
ENVOY_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")
# The capped listener's max_supported_protocol_version, in envoy.yaml.
CAPPED_MAX_VERSION = "2025-11-25"
# The listeners' stat_prefix, in envoy.yaml.
MAIN_STAT_PREFIX = "ingress_http"
CAPPED_STAT_PREFIX = "ingress_http_capped"
# The MCP filter's counters, under http.<stat_prefix>.mcp.
MCP_FILTER_COUNTERS = ("requests_rejected", "invalid_json", "body_too_large",
                       "duplicate_keys_rejected", "header_mismatch")
CLIENT_INFO = {"name": "envoy-mcp-e2e-client", "version": "1.0.0"}
TOOL = "get_weather"
ARGUMENTS = {"city": "Paris"}
# What mcp_server.py's get_weather returns for ARGUMENTS.
EXPECTED_TEXT = "Paris: sunny, 22C"
# TOOL as a base64-encoded MCP header value. The SDK encodes only values that need it.
BASE64_TOOL = f"=?base64?{base64.b64encode(TOOL.encode()).decode()}?="
TIMEOUT_SECONDS = 30


def parse_args():
    parser = argparse.ArgumentParser(description="The MCP client of the MCP filter E2E test.")
    # Where Envoy and the MCP server are: 127.0.0.1 by default; in Docker Compose, the envoy and
    # mcp-server services.
    parser.add_argument("--envoy-host", default="127.0.0.1", help="Envoy's host")
    parser.add_argument(
        "--backend-host", default="127.0.0.1", help="mcp_server.py's host, in Envoy's config")
    parser.add_argument("--port", type=int, required=True, help="Envoy's main listener port")
    parser.add_argument(
        "--capped-port", type=int, required=True, help="Envoy's capped listener port")
    parser.add_argument("--admin-port", type=int, required=True, help="Envoy's admin port")
    parser.add_argument("--backend-port", type=int, required=True, help="mcp_server.py's port")
    parser.add_argument("--run-dir", type=pathlib.Path, required=True)
    parser.add_argument("--skip", default="", help="comma-separated names of cases not to run")
    return parser.parse_args()


class Results:
    """Prints each case and check as it runs, and remembers the failed and skipped cases."""

    def __init__(self):
        self.case = None
        self.failed = []
        self.skipped = []

    def start(self, name, what, needs):
        self.case = name
        print()
        print(f"[{name}] {what}")
        if needs:
            print(f"        needs: {needs}")

    def skip(self, name, what):
        self.skipped.append(name)
        print()
        print(f"[{name}] {what}")
        print("  SKIP  not run: listed in SKIP_CASES")

    def check(self, ok, what):
        print(("  ok    " if ok else "  FAIL  ") + what)
        if not ok and self.case not in self.failed:
            self.failed.append(self.case)

    def case_failed(self):
        return self.case in self.failed

    def summary(self, total):
        run = total - len(self.skipped)
        print()
        print(f"Cases: {run} of {total} run, {run - len(self.failed)} passed, "
              f"{len(self.failed)} failed")
        if self.failed:
            print(f"Failed: {', '.join(self.failed)}")
        if self.skipped:
            print(f"Skipped with SKIP_CASES, so not checked: {', '.join(self.skipped)}")

    def exit_code(self):
        return 1 if self.failed else 0


def describe(error):
    """One line for an exception, from inside any exception groups anyio wrapped it in."""
    while getattr(error, "exceptions", None):
        error = error.exceptions[0]
    text = str(error).strip().partition("\n")[0][:200]
    if not text and isinstance(error, TimeoutError):
        text = f"took more than {TIMEOUT_SECONDS}s"
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def read_json_lines(path):
    """The JSON objects in a file of one per line. Skips a line that is still being written."""
    objects = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                objects.append(json.loads(line))
            except ValueError:
                pass
    return objects


def wait_for_access_log(args, ready, settle_seconds=0):
    """Envoy's access log entries, as soon as ready(entries) is true, or after 10 seconds.

    Envoy writes a request's entry when the request ends, and flushes the file every 200 ms
    (the envoy service's --file-flush-interval-msec). settle_seconds then waits for any other
    entries, for checks that there are none.
    """
    path = args.run_dir / "access.log"
    deadline = time.monotonic() + 10
    entries = read_json_lines(path)
    while not ready(entries) and time.monotonic() < deadline:
        time.sleep(0.1)
        entries = read_json_lines(path)
    if settle_seconds:
        time.sleep(settle_seconds)
        entries = read_json_lines(path)
    return entries


def missing(value):
    """Whether an access log field has no value, which Envoy logs as null (or "-")."""
    return value is None or value == "-"


def server_requests(args):
    """The requests that reached mcp_server.py, from its request log.

    The server writes a request's line before it answers, so the line is there by the time the
    answer reaches the client.
    """
    return read_json_lines(args.run_dir / "backend_requests.jsonl")


def sdk_requests(records):
    """The requests to the MCP endpoint that the SDK client sent: those with no X-E2E-Case."""
    return [
        record for record in records
        if record.get("path") == "/mcp" and "x-e2e-case" not in (record.get("headers") or {})
    ]


def summarize(record):
    """A request in the server's request log, in one line."""
    headers = record.get("headers") or {}
    return (f"{record.get('method')} {record.get('path')}"
            f" version={headers.get(MCP_PROTOCOL_VERSION_HEADER)}"
            f" method={headers.get(MCP_METHOD_HEADER)} name={headers.get(MCP_NAME_HEADER)}"
            f" session={headers.get('mcp-session-id')} -> {record.get('status')}"
            f" new_session={record.get('response_mcp_session_id')}")


def read_stats(args):
    """Envoy's stats: the text of its admin /stats, and the counters in it by name."""
    text = urllib.request.urlopen(
        f"http://{args.envoy_host}:{args.admin_port}/stats", timeout=10).read().decode()
    counters = {}
    for line in text.splitlines():
        name, _, value = line.partition(": ")
        if value.strip().isdigit():
            counters[name] = int(value)
    return text, counters


def backend_address(args):
    """The upstream host that Envoy logs for a request that it forwarded to mcp_server.py.

    Envoy logs the address that it connected to. For a backend host that is a name, such as Docker
    Compose's mcp-server, that is the address that the name resolves to.
    """
    return f"{socket.gethostbyname(args.backend_host)}:{args.backend_port}"


def mcp_counters(args, stat_prefix):
    """The MCP filter's counters on the listener with this stat_prefix."""
    _, counters = read_stats(args)
    return {name: counters.get(f"http.{stat_prefix}.mcp.{name}") for name in MCP_FILTER_COUNTERS}


def check_counters(results, before, after, expected):
    """Checks that each MCP filter counter went up by expected[name], and the others not at all."""
    if None in before.values() or None in after.values():
        results.check(False, f"the MCP filter's counters are in Envoy's stats (got {after})")
        return
    changes = {name: after[name] - before[name] for name in MCP_FILTER_COUNTERS}
    wanted = {name: expected.get(name, 0) for name in MCP_FILTER_COUNTERS}
    results.check(
        changes == wanted,
        f"MCP filter counters: {describe_changes(wanted)} (got {describe_changes(changes)})")


def describe_changes(changes):
    """Counter changes, such as 'header_mismatch +1, others unchanged'."""
    changed = [f"{name} +{change}" for name, change in changes.items() if change]
    return ", ".join(changed + ["others unchanged"]) if changed else "all unchanged"


def sdk_client(url):
    """The SDK's client for an Envoy listener, pinned to PROTOCOL_VERSION."""
    return Client(
        url,
        # A modern protocol version as the mode: the client adopts it with no initialize handshake
        # and no server/discover probe, and does not fall back to the handshake. The default mode,
        # "auto", would probe server/discover, and fall back to the handshake if that failed.
        mode=PROTOCOL_VERSION,
        # No response cache, so that every call goes through Envoy to the server.
        cache=None,
        client_info=Implementation(**CLIENT_INFO),
        read_timeout_seconds=TIMEOUT_SECONDS)


def run_async(results, function):
    """Runs an async function, for up to TIMEOUT_SECONDS. An exception is a failed check."""

    async def run():
        with anyio.fail_after(TIMEOUT_SECONDS):
            await function()

    try:
        anyio.run(run)
    # Whatever went wrong, in the SDK, Envoy or the server, is a failed check.
    except Exception as error:
        results.check(False, f"the SDK client through Envoy: {describe(error)}")


def listener_entries(entries, port):
    """The access log entries of the SDK client's requests to the listener on this port."""
    return [
        entry for entry in entries
        if str(entry.get("listener_port")) == str(port) and missing(entry.get("e2e_case"))
    ]


def check_sdk_stateless_tools(results, args):
    url = f"http://{args.envoy_host}:{args.port}/mcp"
    requests_before = len(sdk_requests(server_requests(args)))
    counters_before = mcp_counters(args, MAIN_STAT_PREFIX)

    async def session():
        async with sdk_client(url) as client:
            results.check(
                client.protocol_version == PROTOCOL_VERSION,
                f"the client uses protocol version {PROTOCOL_VERSION} "
                f"(got {client.protocol_version})")

            listed = await client.list_tools()
            names = [tool.name for tool in listed.tools]
            results.check(names == [TOOL], f"tools/list returned [{TOOL}] (got {names})")

            result = await client.call_tool(TOOL, ARGUMENTS)
            texts = [block.text for block in result.content if isinstance(block, TextContent)]
            results.check(
                not result.is_error and texts == [EXPECTED_TEXT],
                f"tools/call {TOOL}({json.dumps(ARGUMENTS)}) returned {EXPECTED_TEXT!r} "
                f"(got {texts}, isError={result.is_error})")

    run_async(results, session)

    # Exactly these requests, in this order, each with the 2026-07-28 headers and no session.
    expected = (("tools/list", None), ("tools/call", TOOL))
    entries = listener_entries(
        wait_for_access_log(
            args, lambda entries: len(listener_entries(entries, args.port)) >= len(expected),
            settle_seconds=0.5), args.port)
    got = [(entry.get("method"), entry.get("mcp_method")) for entry in entries]
    results.check(
        got == [("POST", method) for method, _ in expected],
        "Envoy logged two requests, POST tools/list and POST tools/call, and no other: no "
        f"initialize, server/discover, GET or DELETE (got {got})")
    upstream = backend_address(args)
    for entry, (method, name) in zip(entries, expected):
        results.check(
            entry.get("response_code") == 200 and entry.get("upstream_host") == upstream
            and entry.get("response_flags") == "-",
            f"{method}: went through Envoy to the server at {upstream}, which answered 200, "
            f"with no response flags (got {entry.get('response_code')} from "
            f"{entry.get('upstream_host')}, flags {entry.get('response_flags')})")
        name_ok = entry.get("mcp_name") == name if name else missing(entry.get("mcp_name"))
        name_header = f", Mcp-Name: {name}" if name else ""
        results.check(
            entry.get("mcp_protocol_version") == PROTOCOL_VERSION
            and entry.get("mcp_method") == method and name_ok
            and missing(entry.get("mcp_session_id")),
            f"{method}: had the headers MCP-Protocol-Version: {PROTOCOL_VERSION}, Mcp-Method: "
            f"{method}{name_header}, and no Mcp-Session-Id (got "
            f"{entry.get('mcp_protocol_version')}, {entry.get('mcp_method')}, "
            f"{entry.get('mcp_name')}, {entry.get('mcp_session_id')})")
        # The attributes the MCP filter parsed from the body (attribute_source: BODY): jsonrpc,
        # id, method, params.name for tools/call, and params._meta, which it copies whole. The
        # SDK's params._meta is the 2026-07-28 envelope that the raw cases send too, envelope():
        # the protocol version, which the filter checks against the header; the client info; and
        # the client capabilities, an object, which the filter requires in every request. This
        # client registers no callbacks, such as for sampling, so it advertises no capabilities.
        mcp = entry.get("mcp") if isinstance(entry.get("mcp"), dict) else {}
        params = mcp.get("params") if isinstance(mcp.get("params"), dict) else {}
        name_param = f", params.name {name}" if name else ""
        results.check(
            mcp.get("status") == "mcp_ok" and mcp.get("is_mcp_request") is True
            and mcp.get("jsonrpc") == "2.0" and "id" in mcp and mcp.get("method") == method
            and params.get("name") == name and params.get("_meta") == envelope(),
            f"{method}: the MCP filter parsed the body as MCP: jsonrpc 2.0, an id, method "
            f"{method}{name_param}, and params._meta {json.dumps(envelope())} "
            f"(got {json.dumps(mcp)})")

    got = [summarize(record) for record in sdk_requests(server_requests(args))[requests_before:]]
    wanted = [
        summarize({
            "method": "POST",
            "path": "/mcp",
            "status": 200,
            "headers": {
                MCP_PROTOCOL_VERSION_HEADER: PROTOCOL_VERSION,
                MCP_METHOD_HEADER: method,
                MCP_NAME_HEADER: name
            }
        }) for method, name in expected
    ]
    results.check(
        got == wanted,
        f"the server received the two requests, with no Mcp-Session-Id, and answered both 200 "
        f"without creating a session (got {got})")

    check_counters(results, counters_before, mcp_counters(args, MAIN_STAT_PREFIX), {})


def check_sdk_unsupported_version(results, args):
    url = f"http://{args.envoy_host}:{args.capped_port}/mcp"
    requests_before = len(sdk_requests(server_requests(args)))
    counters_before = mcp_counters(args, CAPPED_STAT_PREFIX)
    supported = [version for version in ENVOY_PROTOCOL_VERSIONS if version <= CAPPED_MAX_VERSION]
    message = f"Unsupported MCP protocol version: {PROTOCOL_VERSION}"
    data = {"supported": supported, "requested": PROTOCOL_VERSION}

    async def session():
        async with sdk_client(url) as client:
            try:
                listed = await client.list_tools()
            except MCPError as error:
                results.check(
                    error.code == UNSUPPORTED_PROTOCOL_VERSION and error.message == message
                    and error.data == data,
                    f"tools/list failed with the MCP filter's error {UNSUPPORTED_PROTOCOL_VERSION} "
                    f"{message!r}, data {json.dumps(data)} (got {error.code} {error.message!r}, "
                    f"data {json.dumps(error.data)})")
            else:
                results.check(
                    False, f"tools/list failed with error {UNSUPPORTED_PROTOCOL_VERSION} "
                    f"(it returned {[tool.name for tool in listed.tools]})")

    run_async(results, session)

    entries = listener_entries(
        wait_for_access_log(
            args, lambda entries: listener_entries(entries, args.capped_port), settle_seconds=0.5),
        args.capped_port)
    got = [(e.get("method"), e.get("mcp_method"), e.get("mcp_protocol_version")) for e in entries]
    results.check(
        got == [("POST", "tools/list", PROTOCOL_VERSION)],
        f"Envoy logged one request, the POST of tools/list at {PROTOCOL_VERSION}, and no other: "
        f"the client did not fall back to the initialize handshake (got {got})")
    entry = entries[0] if len(entries) == 1 else {}
    mcp = entry.get("mcp") if isinstance(entry.get("mcp"), dict) else {}
    results.check(
        entry.get("response_code") == 400 and missing(entry.get("upstream_host"))
        and mcp.get("status") == "mcp_not_jsonrpc" and mcp.get("is_mcp_request") is False,
        "the MCP filter answered 400 itself, with no upstream host, and its metadata has status "
        f"mcp_not_jsonrpc (got {entry.get('response_code')} from {entry.get('upstream_host')}, "
        f"metadata {json.dumps(entry.get('mcp'))})")

    got = [summarize(record) for record in sdk_requests(server_requests(args))[requests_before:]]
    results.check(not got, f"the request did not reach the server (got {got})")

    check_counters(results, counters_before, mcp_counters(args, CAPPED_STAT_PREFIX), {})


@dataclasses.dataclass
class RawCase:
    """A request sent with raw HTTP to Envoy's main listener, and what must happen to it."""
    name: str
    what: str
    headers: dict
    body: dict | None = None
    http_method: str = "POST"
    # The response: its status, its body as a JSON-RPC message or as text, and some headers.
    status: int = 400
    json_body: dict | None = None
    text_body: str | None = None
    response_headers: dict = dataclasses.field(default_factory=dict)
    # Whether the request must reach the server, and the text of the tool result it returns. The
    # response of a request that reaches the server is the server's, whatever its status.
    reaches_server: bool = False
    result_text: str | None = None
    # How much each MCP filter counter must go up. The others must not.
    counters: dict = dataclasses.field(default_factory=dict)
    # The status in the MCP filter's dynamic metadata, or None if the filter must set none.
    metadata_status: str | None = "mcp_not_jsonrpc"
    # Attributes that the MCP filter must have parsed from the body into its dynamic metadata, by
    # their dotted path in it, each with its value, or ABSENT if the metadata must not have it.
    parsed: dict = dataclasses.field(default_factory=dict)
    # Functionality the case needs that this branch may not have.
    needs: str = ""


# In RawCase.parsed: the MCP filter's dynamic metadata must not have this attribute.
ABSENT = object()


def envelope(protocol_version=PROTOCOL_VERSION, client_capabilities=True):
    """The params._meta of a 2026-07-28 request, as the SDK sends it.

    sdk-stateless-tools checks that the SDK's requests have exactly this params._meta.
    """
    meta = {PROTOCOL_VERSION_META_KEY: protocol_version, CLIENT_INFO_META_KEY: CLIENT_INFO}
    if client_capabilities:
        meta[CLIENT_CAPABILITIES_META_KEY] = {}
    return meta


def modern_message(method, params, request_id=None, meta=None):
    """A JSON-RPC request, or without request_id a notification, with params._meta."""
    message = {"jsonrpc": "2.0"}
    if request_id is not None:
        message["id"] = request_id
    message["method"] = method
    message["params"] = {**params, "_meta": envelope() if meta is None else meta}
    return message


def modern_headers(method=None, name=None, version=PROTOCOL_VERSION):
    """The HTTP headers of a 2026-07-28 POST, as the SDK sends them."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        MCP_PROTOCOL_VERSION_HEADER: version,
    }
    if method is not None:
        headers[MCP_METHOD_HEADER] = method
    if name is not None:
        headers[MCP_NAME_HEADER] = name
    return headers


def jsonrpc_error(request_id, code, message, data=None):
    """A JSON-RPC error response, as the MCP filter, or the server, sends it."""
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def raw_cases():
    call = {"name": TOOL, "arguments": ARGUMENTS}
    mismatch = "MCP header attributes do not match request body"
    no_capabilities = f"Missing required params._meta field: {CLIENT_CAPABILITIES_META_KEY}"
    no_protocol_version = f"Missing or invalid params._meta field: {PROTOCOL_VERSION_META_KEY}"
    return [
        RawCase(
            name="base64-mcp-name",
            what=f"tools/call with Mcp-Name base64-encoded ({BASE64_TOOL}), which the SDK does "
            "only for names that need it: the filter decodes it, and forwards the request",
            headers=modern_headers("tools/call", BASE64_TOOL),
            body=modern_message("tools/call", call, "base64-mcp-name"),
            status=200,
            reaches_server=True,
            result_text=EXPECTED_TEXT,
            metadata_status="mcp_ok",
            parsed={"method": "tools/call", "params.name": TOOL}),
        RawCase(
            name="missing-mcp-method",
            what="tools/list without the Mcp-Method header",
            headers=modern_headers(),
            body=modern_message("tools/list", {}, "missing-mcp-method"),
            json_body=jsonrpc_error(None, HEADER_MISMATCH, "Missing required Mcp-Method header"),
            counters={"header_mismatch": 1}),
        RawCase(
            name="missing-mcp-name",
            what="tools/call without the Mcp-Name header",
            headers=modern_headers("tools/call"),
            body=modern_message("tools/call", call, "missing-mcp-name"),
            json_body=jsonrpc_error(None, HEADER_MISMATCH, "Missing required Mcp-Name header"),
            counters={"header_mismatch": 1}),
        RawCase(
            name="invalid-base64-mcp-name",
            what="tools/call whose Mcp-Name header is not valid base64: =?base64?%%%?=",
            headers=modern_headers("tools/call", "=?base64?%%%?="),
            body=modern_message("tools/call", call, "invalid-base64-mcp-name"),
            json_body=jsonrpc_error(
                None, HEADER_MISMATCH, "Invalid Base64-encoded Mcp-Name header"),
            counters={"header_mismatch": 1}),
        RawCase(
            name="mcp-method-mismatch",
            what="Mcp-Method: tools/list on a tools/call body",
            headers=modern_headers("tools/list"),
            body=modern_message("tools/call", call, "mcp-method-mismatch"),
            json_body=jsonrpc_error("mcp-method-mismatch", HEADER_MISMATCH, mismatch),
            counters={"header_mismatch": 1}),
        RawCase(
            name="mcp-name-mismatch",
            what=f"Mcp-Name: {TOOL} on a tools/call of another tool, get_forecast",
            headers=modern_headers("tools/call", TOOL),
            body=modern_message(
                "tools/call", {**call, "name": "get_forecast"}, "mcp-name-mismatch"),
            json_body=jsonrpc_error("mcp-name-mismatch", HEADER_MISMATCH, mismatch),
            counters={"header_mismatch": 1}),
        RawCase(
            name="protocol-version-mismatch",
            what=f"MCP-Protocol-Version: {PROTOCOL_VERSION} on a body whose params._meta has "
            "protocol version 2025-11-25",
            headers=modern_headers("tools/list"),
            body=modern_message(
                "tools/list", {}, "protocol-version-mismatch",
                envelope(protocol_version="2025-11-25")),
            json_body=jsonrpc_error(
                "protocol-version-mismatch", HEADER_MISMATCH,
                "MCP-Protocol-Version header does not match request body"),
            counters={"header_mismatch": 1}),
        RawCase(
            name="unknown-protocol-version",
            what="tools/list at protocol version 2099-01-01, which the MCP filter does not know",
            headers=modern_headers("tools/list", version="2099-01-01"),
            body=modern_message(
                "tools/list", {}, "unknown-protocol-version",
                envelope(protocol_version="2099-01-01")),
            json_body=jsonrpc_error(
                None, UNSUPPORTED_PROTOCOL_VERSION, "Unsupported MCP protocol version: 2099-01-01",
                {"supported": list(ENVOY_PROTOCOL_VERSIONS), "requested": "2099-01-01"})),
        # Every 2026-07-28 request, unlike a notification, must have client capabilities in
        # params._meta: the MCP filter answers -32602 for one that has none.
        RawCase(
            name="missing-client-capabilities",
            what="tools/list whose params._meta has the protocol version and the client info, "
            f"but no {CLIENT_CAPABILITIES_META_KEY}",
            headers=modern_headers("tools/list"),
            body=modern_message(
                "tools/list", {}, "missing-client-capabilities",
                envelope(client_capabilities=False)),
            json_body=jsonrpc_error(
                "missing-client-capabilities", INVALID_PARAMS, no_capabilities)),
        # The filter checks params._meta's protocol version before its client capabilities
        # (envoyproxy/envoy#48720), so a request with no params._meta fails the first check.
        RawCase(
            name="missing-meta",
            what="tools/list with no params at all, so no params._meta: no protocol version, "
            "client info or client capabilities",
            headers=modern_headers("tools/list"),
            body={"jsonrpc": "2.0", "id": "missing-meta", "method": "tools/list"},
            json_body=jsonrpc_error("missing-meta", INVALID_PARAMS, no_protocol_version)),
        # Before envoyproxy/envoy#47862, the filter's parser lost its place in the body after an
        # object whose key has dots, such as the client info in params._meta, so it lost an id
        # that came after params. With no id, the request looked like a notification, which needs
        # no client capabilities, and the filter forwarded it.
        RawCase(
            name="missing-client-capabilities-id-last",
            what="missing-client-capabilities, with the id last: after params, whose _meta has "
            f"{CLIENT_INFO_META_KEY}, an object whose key has dots",
            headers=modern_headers("tools/list"),
            body={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {"_meta": envelope(client_capabilities=False)},
                "id": "missing-client-capabilities-id-last",
            },
            json_body=jsonrpc_error(
                "missing-client-capabilities-id-last", INVALID_PARAMS, no_capabilities)),
        RawCase(
            name="session-delete",
            what="DELETE with an Mcp-Session-Id: there are no sessions to end at 2026-07-28",
            http_method="DELETE",
            headers={MCP_PROTOCOL_VERSION_HEADER: PROTOCOL_VERSION, "Mcp-Session-Id": "e2e"},
            status=405,
            text_body=f"MCP DELETE is not supported for protocol version {PROTOCOL_VERSION}",
            response_headers={"allow": "POST"},
            metadata_status=None),
        RawCase(
            name="sse-get",
            what="GET of an SSE stream: there are no GET streams at 2026-07-28",
            http_method="GET",
            headers={MCP_PROTOCOL_VERSION_HEADER: PROTOCOL_VERSION, "Accept": "text/event-stream"},
            status=405,
            text_body=f"MCP GET with SSE is not supported for protocol version {PROTOCOL_VERSION}",
            response_headers={"allow": "POST"},
            metadata_status=None),
        # The legacy handshake, at 2026-07-28. That version drops the initialize handshake, but the
        # spec does not require an intermediary to reject its messages. The MCP filter has no rule
        # for them: it forwards them, as it does any 2026-07-28 request whose headers match its
        # body and whose params._meta has client capabilities (which a notification does not
        # need). The MCP JSON-REST bridge rejects them itself, but it is not in this test. So these
        # cases check that Envoy forwards them, and passes on the server's own response, not an
        # error from the filter. The responses that they expect, 404 and 202, are what the pinned
        # SDK, mcp 2.2.0, answers, not protocol requirements: other servers, and other SDK
        # versions, may answer differently and still follow the spec. mcp 2.0.0, for example,
        # refuses the notification (400, -32600). See README.md.
        RawCase(
            name="legacy-initialize",
            what="initialize, the legacy handshake, at 2026-07-28: the MCP filter forwards it, and "
            "the server, on the pinned SDK, mcp 2.2.0, answers 404, -32601, as for any method that "
            "it does not have at that version",
            headers=modern_headers("initialize"),
            body=modern_message(
                "initialize", {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO
                }, "legacy-initialize"),
            status=404,
            json_body=jsonrpc_error(
                "legacy-initialize", METHOD_NOT_FOUND, "Method not found", "initialize"),
            reaches_server=True,
            metadata_status="mcp_ok",
            parsed={
                "jsonrpc": "2.0",
                "id": "legacy-initialize",
                "method": "initialize",
                # The filter's extraction rules for initialize.
                "params.protocolVersion": PROTOCOL_VERSION,
                "params.clientInfo.name": CLIENT_INFO["name"],
                "params._meta": envelope(),
            }),
        RawCase(
            name="legacy-initialized-notification",
            what="notifications/initialized, which ends the legacy handshake, at 2026-07-28: the "
            "MCP filter forwards it, and the server, on the pinned SDK, mcp 2.2.0, accepts it, 202 "
            "with no body, as it does any notification at that version",
            headers=modern_headers("notifications/initialized"),
            body=modern_message("notifications/initialized", {}),
            status=202,
            text_body="",
            reaches_server=True,
            metadata_status="mcp_ok",
            parsed={
                "jsonrpc": "2.0",
                "id": ABSENT,
                "method": "notifications/initialized",
                "params._meta": envelope(),
            }),
    ]


def send(host, port, case):
    """Sends the case's request to Envoy. Returns the status, headers and body of the response."""
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        connection.request(
            case.http_method,
            "/mcp",
            body=None if case.body is None else json.dumps(case.body),
            # How the checks find this request in Envoy's access log and the server's request log.
            headers={**case.headers, "x-e2e-case": case.name})
        response = connection.getresponse()
        headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, headers, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


def jsonrpc_response(content_type, body, request_id):
    """The JSON-RPC response to request_id in a JSON body, or in an SSE stream."""
    if content_type.startswith("text/event-stream"):
        payloads = [line[len("data:"):] for line in body.splitlines() if line.startswith("data:")]
    else:
        payloads = [body]
    for payload in payloads:
        try:
            message = json.loads(payload)
        except ValueError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message
    return None


def check_raw_response(results, case, status, headers, body):
    content_type = headers.get("content-type", "")
    if case.json_body is not None:
        try:
            message = json.loads(body)
        except ValueError:
            message = None
        results.check(
            status == case.status and content_type == "application/json"
            and message == case.json_body,
            f"{case.status}, application/json: {json.dumps(case.json_body)} "
            f"(got {status}, {content_type}: {body[:300]})")
    if case.text_body is not None:
        wanted = repr(case.text_body) if case.text_body else "no body"
        results.check(
            status == case.status and body == case.text_body,
            f"{case.status}: {wanted} (got {status}: {body[:300]!r})")
    for name, value in case.response_headers.items():
        results.check(
            headers.get(name) == value,
            f"response header {name}: {value} (got {headers.get(name)})")
    if case.result_text is not None:
        result = (jsonrpc_response(content_type, body, case.body["id"]) or {}).get("result") or {}
        blocks = result.get("content") or []
        texts = [block.get("text") for block in blocks if block.get("type") == "text"]
        results.check(
            status == case.status and not result.get("isError") and texts == [case.result_text],
            f"{case.status}, with the tool result {case.result_text!r} "
            f"(got {status}, {content_type}: {body[:300]})")


def parsed_value(mcp, path):
    """The value at a dotted path in the MCP filter's dynamic metadata, or ABSENT."""
    value = mcp
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return ABSENT
        value = value[key]
    return value


def check_metadata(results, case, mcp):
    """Checks the MCP filter's dynamic metadata for a raw case's request, from the access log."""
    if case.metadata_status is None:
        results.check(
            not isinstance(mcp, dict),
            f"access log: the MCP filter set no dynamic metadata (got {json.dumps(mcp)})")
        return
    got = json.dumps(mcp)
    mcp = mcp if isinstance(mcp, dict) else {}
    is_mcp = case.metadata_status == "mcp_ok"
    ok = mcp.get("status") == case.metadata_status and mcp.get("is_mcp_request") is is_mcp
    wanted = f"status {case.metadata_status}, is_mcp_request {str(is_mcp).lower()}"
    # The attributes the MCP filter parsed from the body (attribute_source: BODY).
    for path, value in case.parsed.items():
        ok = ok and parsed_value(mcp, path) == value
        if value is ABSENT:
            wanted += f", no {path}"
        else:
            wanted += f", {path} {value if isinstance(value, str) else json.dumps(value)}"
    results.check(ok, f"access log: the MCP filter's metadata has {wanted} (got {got})")


def check_raw_case(results, args, case):
    counters_before = mcp_counters(args, MAIN_STAT_PREFIX)
    status, headers, body = send(args.envoy_host, args.port, case)
    counters_after = mcp_counters(args, MAIN_STAT_PREFIX)
    check_raw_response(results, case, status, headers, body)

    records = [
        record for record in server_requests(args)
        if (record.get("headers") or {}).get("x-e2e-case") == case.name
    ]
    if case.reaches_server:
        # Envoy forwards the MCP headers as they are, and the response is the server's: the server
        # logs the status that it answers with.
        names = (MCP_PROTOCOL_VERSION_HEADER, MCP_METHOD_HEADER, MCP_NAME_HEADER)
        sent = {name: case.headers.get(name) for name in names}
        received = [{name: (r.get("headers") or {}).get(name) for name in names} for r in records]
        statuses = [record.get("status") for record in records]
        results.check(
            received == [sent] and statuses == [case.status],
            f"the server received the request once, with the same MCP headers, and answered "
            f"{case.status} (got {[summarize(record) for record in records]})")
    else:
        results.check(
            not records,
            f"the request did not reach the server (got {[summarize(r) for r in records]})")

    check_counters(results, counters_before, counters_after, case.counters)

    entries = [
        entry for entry in wait_for_access_log(
            args, lambda entries: any(entry.get("e2e_case") == case.name for entry in entries))
        if entry.get("e2e_case") == case.name
    ]
    if len(entries) != 1:
        results.check(False, f"Envoy logged the request once (got {len(entries)} entries)")
        return
    entry = entries[0]
    code = entry.get("response_code")
    upstream = backend_address(args)
    if case.reaches_server:
        # Envoy's response code details are via_upstream for a response that came from the
        # upstream, whatever its status, and name the local reply for one that Envoy made itself.
        details = entry.get("response_code_details")
        results.check(
            code == case.status and entry.get("upstream_host") == upstream
            and details == "via_upstream" and entry.get("response_flags") == "-",
            f"access log: went to the server at {upstream}, whose {case.status} Envoy passed on "
            f"(response code details via_upstream), with no response flags (got {code} from "
            f"{entry.get('upstream_host')}, details {details}, flags "
            f"{entry.get('response_flags')})")
    else:
        results.check(
            code == case.status and missing(entry.get("upstream_host")),
            f"access log: Envoy answered {case.status} itself, with no upstream host (got {code} "
            f"from {entry.get('upstream_host')})")
    check_metadata(results, case, entry.get("mcp"))
    if results.case_failed():
        print(f"        access log entry: {json.dumps(entry)}")


def cases():
    """Every case, in the order they run: name, what it sends, what it needs, and its check."""
    return [
        ("sdk-stateless-tools",
         f"the SDK client, pinned to {PROTOCOL_VERSION}, lists the tools and calls {TOOL}: "
         "stateless requests, which reach the server", "", check_sdk_stateless_tools),
        ("sdk-unsupported-version",
         f"the same client, through the listener whose MCP filter supports protocol versions up "
         f"to {CAPPED_MAX_VERSION}: the filter rejects its tools/list", "",
         check_sdk_unsupported_version),
    ] + [(case.name, case.what, case.needs, functools.partial(check_raw_case, case=case))
         for case in raw_cases()]


def main():
    args = parse_args()
    all_cases = cases()
    names = [name for name, _, _, _ in all_cases]
    skip = {name.strip() for name in args.skip.split(",") if name.strip()}
    if skip - set(names):
        sys.exit(f"Unknown cases in SKIP_CASES: {', '.join(sorted(skip - set(names)))}. "
                 f"The cases are: {', '.join(names)}")

    print(f"MCP Python SDK {importlib.metadata.version('mcp')}, protocol version "
          f"{PROTOCOL_VERSION}, through Envoy at {args.envoy_host}:{args.port}, and at "
          f"{args.envoy_host}:{args.capped_port} capped at {CAPPED_MAX_VERSION}")
    results = Results()
    for name, what, needs, check in all_cases:
        if name in skip:
            results.skip(name, what)
            continue
        results.start(name, what, needs)
        try:
            check(results, args)
        # A case that cannot finish, for example because Envoy is gone, is a failed check.
        except Exception as error:
            results.check(False, f"the case did not finish: {describe(error)}")

    try:
        text, _ = read_stats(args)
        (args.run_dir / "stats.txt").write_text(text)
    except OSError as error:
        print(f"Could not save Envoy's stats in stats.txt: {describe(error)}")
    results.summary(len(all_cases))
    sys.exit(results.exit_code())


if __name__ == "__main__":
    main()
