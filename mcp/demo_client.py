"""Developer demo of MCP protocol version 2026-07-28 through Envoy's MCP filter.

docker/client_entrypoint.py runs it in place of mcp_client.py when DEMO=1, with
`mcp_server.py --demo` behind Envoy.
It is a demonstration, not a regression test (mcp_client.py's cases are the regression suite):

1. With the official MCP Python SDK (mcp 2.2.0) pinned to 2026-07-28, it walks through a simulated
   service-operations scenario: the tools of demo_tools.py, called one after another.
2. It shows the per-request protocol information of those stateless requests.
3. With raw HTTP, it sends requests that show how Envoy's MCP filter validates 2026-07-28 requests:
   their MCP headers against the body, the protocol version, and the client capabilities.
4. It exercises server/discover, cache hints and a multi round-trip request, which the SDK client
   and server implement, and which Envoy only forwards.

Everything it prints is observed, not reconstructed:
- the SDK client's requests and responses, recorded as they leave and reach the client, by httpx2
  event hooks on the HTTP client that the SDK's Streamable HTTP transport uses;
- whether Envoy forwarded a request or answered it itself, from Envoy's access log;
- whether the MCP server received it, from the server's request log.
Each request carries an X-E2E-Case header, only so that the demo can find it in those logs. Each
step checks what it observed, and the demo exits 1 if a check fails. See README.md.
"""
import argparse
import base64
import dataclasses
import http.client
import importlib.metadata
import json
import logging
import os
import pathlib
import sys

import anyio
import httpx2
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.inbound import MCP_METHOD_HEADER, MCP_NAME_HEADER, MCP_PROTOCOL_VERSION_HEADER
from mcp.types import (CLIENT_CAPABILITIES_META_KEY, CLIENT_INFO_META_KEY, HEADER_MISMATCH,
                       INVALID_PARAMS, PROTOCOL_VERSION_META_KEY, UNSUPPORTED_PROTOCOL_VERSION,
                       ElicitResult, Implementation)

# The regression suite's helpers for Envoy's access log, the server's request log and Envoy's stats.
from mcp_client import (CAPPED_MAX_VERSION, CAPPED_STAT_PREFIX, ENVOY_PROTOCOL_VERSIONS,
                        MAIN_STAT_PREFIX, PROTOCOL_VERSION, describe_changes, mcp_counters,
                        missing, read_json_lines, read_stats, wait_for_access_log)

# The SDK client's client info, in the _meta of each of its requests.
CLIENT_INFO = {"name": "envoy-mcp-demo-client", "version": "1.0.0"}
# The raw HTTP requests' client info, so that their _meta differs visibly from the SDK client's.
RAW_CLIENT_INFO = {"name": "envoy-mcp-demo-raw-http", "version": "1.0.0"}
# How the demo's operator answers apply_remediation's approval request.
APPROVAL = {"approve": True, "operator": "demo-oncall"}
DEMO_TOOLS = ("list_services", "get_service_health", "get_incident", "recommend_action",
              "apply_remediation")
TIMEOUT_SECONDS = 30
HEADER_NAMES = {
    MCP_PROTOCOL_VERSION_HEADER: "MCP-Protocol-Version",
    MCP_METHOD_HEADER: "Mcp-Method",
    MCP_NAME_HEADER: "Mcp-Name",
    "mcp-session-id": "Mcp-Session-Id",
}


def parse_args():
    parser = argparse.ArgumentParser(description="The MCP 2026-07-28 developer demo through Envoy.")
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
    return parser.parse_args()


class Style:
    """ANSI colors on a terminal; none when the output is not one, or NO_COLOR is set."""

    def __init__(self):
        self.enabled = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def paint(self, code, text):
        return f"\033[{code}m{text}\033[0m" if self.enabled else text


@dataclasses.dataclass
class Exchange:
    """One HTTP request of the SDK client, and its response, as the client saw them."""
    tag: str
    method: str
    headers: dict
    body: dict | None
    status: int | None = None
    response_headers: dict = dataclasses.field(default_factory=dict)
    response_body: dict | None = None

    @property
    def params(self):
        return (self.body or {}).get("params") or {}

    @property
    def result(self):
        return (self.response_body or {}).get("result") or {}


class Recorder:
    """Records the SDK client's HTTP exchanges, with httpx2 event hooks.

    `tag` is the X-E2E-Case header of the requests that follow, by which the demo finds them in
    Envoy's access log and the MCP server's request log.
    """

    def __init__(self):
        self.tag = "demo-sdk"
        self.exchanges = []
        self.pending = {}

    def http_client(self):
        """An httpx2 client for the SDK's Streamable HTTP transport, that records through this."""
        return httpx2.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            event_hooks={"request": [self.on_request], "response": [self.on_response]})

    async def on_request(self, request):
        request.headers["x-e2e-case"] = self.tag
        try:
            body = json.loads(request.content) if request.content else None
        except (ValueError, httpx2.RequestNotRead):
            body = None
        exchange = Exchange(self.tag, request.method, dict(request.headers), body)
        self.exchanges.append(exchange)
        self.pending[id(request)] = exchange

    async def on_response(self, response):
        exchange = self.pending.pop(id(response.request), None)
        if exchange is None:
            return
        exchange.status = response.status_code
        exchange.response_headers = dict(response.headers)
        # The SDK reads a JSON response whole anyway; httpx2 keeps the content for it.
        if response.headers.get("content-type", "").startswith("application/json"):
            await response.aread()
            try:
                exchange.response_body = json.loads(response.content)
            except ValueError:
                pass

    def tagged(self, tag):
        return [exchange for exchange in self.exchanges if exchange.tag == tag]


class Demo:
    """The demo's state: its arguments, the recorder, and the checks so far."""

    def __init__(self, args):
        self.args = args
        self.recorder = Recorder()
        self.style = Style()
        self.section_title = ""
        self.results = []
        self.elicitations = []
        self.expected_counters = {}

    def section(self, title):
        self.section_title = title
        print()
        print(self.style.paint("1;36", "=" * 100))
        print(self.style.paint("1;36", f" {title}"))
        print(self.style.paint("1;36", "=" * 100))

    def step(self, text):
        print()
        print(self.style.paint("1", f"  > {text}"))

    def say(self, actor, text):
        """A line attributed to the component that produced it."""
        print(f"    {self.style.paint('35', f'[{actor}]'.ljust(14))}{text}")

    def detail(self, text):
        print(f"      {self.style.paint('2', text)}")

    def check(self, ok, text):
        ok = bool(ok)
        mark = self.style.paint("32", "✓") if ok else self.style.paint("31", "✗")
        print(f"    {mark} {text}")
        self.results.append((self.section_title, text, ok))
        return ok

    def sdk_client(self, url, **options):
        """The SDK client, pinned to 2026-07-28, and the httpx2 client it records through."""
        http_client = self.recorder.http_client()
        client = Client(
            streamable_http_client(url, http_client=http_client),
            # A modern protocol version as the mode: no initialize handshake, no server/discover
            # probe, and no fallback to the handshake.
            mode=PROTOCOL_VERSION,
            client_info=Implementation(**CLIENT_INFO),
            read_timeout_seconds=TIMEOUT_SECONDS,
            **options)
        return http_client, client

    async def approve(self, context, params):
        """The SDK client's elicitation callback: the operator approves, the same way every time."""
        self.elicitations.append(params)
        return ElicitResult(action="accept", content=APPROVAL)


def compact(value, limit=110):
    """JSON in one line, cut to `limit` characters."""
    text = json.dumps(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def short_key(key):
    """A _meta key without its io.modelcontextprotocol/ prefix."""
    return key.rpartition("/")[2]


def mcp_headers(headers):
    """The MCP headers of a request, as `Name: value` pairs, in the spec's casing."""
    lowered = {name.lower(): value for name, value in headers.items()}
    return "  ".join(f"{HEADER_NAMES[name]}: {lowered[name]}" for name in HEADER_NAMES
                     if name in lowered)


def envoy_entries(args, tag, count=1):
    """Envoy's access log entries of the requests with this X-E2E-Case, once there are `count`."""
    entries = wait_for_access_log(
        args, lambda entries: sum(entry.get("e2e_case") == tag for entry in entries) >= count)
    return [entry for entry in entries if entry.get("e2e_case") == tag]


def backend_records(args, tag):
    """The MCP server's request log lines of the requests with this X-E2E-Case."""
    return [
        record for record in read_json_lines(args.run_dir / "backend_requests.jsonl")
        if (record.get("headers") or {}).get("x-e2e-case") == tag
    ]


def forwarded(entry):
    """Whether Envoy forwarded the request to the MCP server, from its access log entry."""
    return (entry is not None and not missing(entry.get("upstream_host"))
            and entry.get("response_code_details") == "via_upstream")


def handled_by(entry):
    """Who answered the request, from its access log entry, in words."""
    if entry is None:
        return "unknown: Envoy logged no access log entry for it"
    if forwarded(entry):
        return (f"MCP backend: Envoy forwarded it to {entry.get('upstream_host')} (response code "
                f"details: via_upstream)")
    return (f"Envoy MCP filter: a local reply (response code details: "
            f"{entry.get('response_code_details')}); nothing was forwarded")


def show_tagged_path(demo, tag, count=1):
    """Where the requests with this tag went: Envoy's access log, and the server's request log."""
    entries = envoy_entries(demo.args, tag, count)
    records = backend_records(demo.args, tag)
    for entry in entries:
        demo.say("Envoy", f"{entry.get('method')} {entry.get('mcp_method')} -> "
                 f"{entry.get('response_code')}: {handled_by(entry)}")
    statuses = [record.get("status") for record in records]
    demo.say("MCP backend",
             f"received {len(records)} request(s), and answered {statuses}" if records else
             "did not receive it")
    return entries, records


# 1. MCP 2026-07-28 Connection


async def connection(demo, client, url):
    demo.section("1. MCP 2026-07-28 Connection")
    print(f"    SDK client  ->  Envoy {demo.args.envoy_host}:{demo.args.port} (MCP filter -> "
          f"router)  ->  MCP backend {demo.args.backend_host}:{demo.args.backend_port}/mcp")
    demo.step("Connect with the official MCP Python SDK, pinned to protocol version "
              f"{PROTOCOL_VERSION}")
    demo.say("SDK client", f'Client("{url}", mode="{PROTOCOL_VERSION}"), mcp '
             f"{importlib.metadata.version('mcp')}")
    demo.check(client.protocol_version == PROTOCOL_VERSION,
               f"the client uses protocol version {client.protocol_version}")
    demo.check(not demo.recorder.exchanges,
               "connecting sent no HTTP request: no initialize handshake, no server/discover "
               f"probe (got {len(demo.recorder.exchanges)} requests)")


# 2. Tool Discovery


async def tool_discovery(demo, client):
    demo.section("2. Tool Discovery")
    demo.step("tools/list")
    demo.recorder.tag = "demo-sdk-tools-list"
    listed = await client.list_tools()
    for tool in listed.tools:
        parameters = ", ".join((tool.input_schema or {}).get("properties", {}))
        description = ((tool.description or "").strip().splitlines() or [""])[0]
        demo.say("MCP backend", f"{tool.name}({parameters}): {description}")
    names = [tool.name for tool in listed.tools]
    demo.check(all(name in names for name in DEMO_TOOLS),
               f"the server lists the demo's tools: {', '.join(DEMO_TOOLS)}")

    exchanges = demo.recorder.tagged("demo-sdk-tools-list")
    if not demo.check(len(exchanges) == 1, f"one HTTP request (got {len(exchanges)})"):
        return
    exchange = exchanges[0]
    print()
    print("    Observed request, as the SDK client sent it:")
    demo.detail(f"{exchange.method} /mcp  {mcp_headers(exchange.headers)}")
    demo.detail(f"Accept: {exchange.headers.get('accept')}  Content-Type: "
                f"{exchange.headers.get('content-type')}")
    demo.detail(f"body: {compact({k: v for k, v in exchange.body.items() if k != 'params'})}")
    for key, value in exchange.params.get("_meta", {}).items():
        demo.detail(f"params._meta {key}: {json.dumps(value)}")
    print("    Observed response, after Envoy:")
    demo.detail(f"HTTP {exchange.status}, {exchange.response_headers.get('content-type')}, "
                f"Mcp-Session-Id: {exchange.response_headers.get('mcp-session-id', 'none')}")
    result = exchange.result
    demo.detail(f"result: {len(result.get('tools', []))} tools, resultType "
                f"{result.get('resultType')}, ttlMs {result.get('ttlMs')}, cacheScope "
                f"{result.get('cacheScope')} (cache hints from the MCP backend; see section 8)")


# 3. Multi-step Tool Execution


async def call(demo, client, tool, arguments):
    """Calls a tool through Envoy, under its own X-E2E-Case tag, and returns the SDK's result."""
    demo.recorder.tag = f"demo-sdk-{tool}-{len(demo.recorder.exchanges) + 1}"
    result = await client.call_tool(tool, arguments)
    demo.say("SDK client", f"call_tool({tool!r}, {json.dumps(arguments)}) -> "
             f"isError={result.is_error}")
    return result


async def multi_step(demo, client):
    demo.section("3. Multi-step Tool Execution")
    demo.step("Step 1: list_services()")
    services = (await call(demo, client, "list_services", {})).structured_content or {}
    for service in services.get("services", []):
        demo.say("MCP backend", f"{service['name']:<14} team {service['team']:<12} tier "
                 f"{service['tier']:<9} version {service['version']}")
    names = [service["name"] for service in services.get("services", [])]
    demo.check(bool(names), f"{len(names)} services")

    demo.step("Step 2: get_service_health(service) for each service")
    degraded = None
    for name in names:
        health = (await call(demo, client, "get_service_health", {"service": name}))
        data = health.structured_content or {}
        demo.say("MCP backend", f"{name:<14} {data.get('status', '?'):<9} errors "
                 f"{data.get('error_rate_percent')}% (SLO {data.get('slo_error_rate_percent')}%), "
                 f"p99 {data.get('p99_latency_ms')} ms, {data.get('requests_per_minute')} req/min")
        if degraded is None and data.get("status") != "healthy":
            degraded = name
    if not demo.check(degraded is not None, f"found a service that is not healthy: {degraded}"):
        return None

    demo.step(f"Step 3: get_incident({degraded!r})")
    incident = (await call(demo, client, "get_incident", {"service": degraded})).structured_content
    incident = incident or {}
    for field in ("incident_id", "severity", "status", "title", "started_at", "impact",
                  "suspected_cause", "related_change"):
        demo.say("MCP backend", f"{field}: {incident.get(field)}")
    incident_id = incident.get("incident_id")
    if not demo.check(bool(incident_id), f"the open incident is {incident_id}"):
        return None

    demo.step(f"Step 4: recommend_action({degraded!r}, {incident_id!r})")
    advice = (await call(demo, client, "recommend_action",
                         {"service": degraded, "incident_id": incident_id})).structured_content
    advice = advice or {}
    demo.say("MCP backend", f"{advice.get('action')}: {advice.get('summary')} (risk "
             f"{advice.get('risk')}, about {advice.get('expected_recovery_minutes')} minutes, "
             f"{advice.get('runbook')})")
    for number, step in enumerate(advice.get("steps", []), 1):
        demo.detail(f"{number}. {step}")
    demo.check(bool(advice.get("action")), f"recommended action: {advice.get('action')}")

    demo.step("A tool error: get_service_health('billing'), a service that does not exist")
    error = await call(demo, client, "get_service_health", {"service": "billing"})
    text = " ".join(getattr(block, "text", "") for block in error.content)
    demo.say("MCP backend", text)
    demo.check(error.is_error, "the MCP backend answered with a tool error (isError: true, in an "
               "HTTP 200 that Envoy forwarded), not a protocol error")
    return degraded, incident_id


# 4. Stateless Request Metadata


def stateless_metadata(demo):
    demo.section("4. Stateless Request Metadata")
    exchanges = list(demo.recorder.exchanges)
    print("    Every request that the SDK client sent so far, as it sent it, with what Envoy and "
          "the MCP backend saw:")
    print()
    print(f"    {'#':<3}{'Mcp-Method':<12}{'Mcp-Name':<20}{'MCP-Protocol-Version':<22}"
          f"{'Mcp-Session-Id':<16}{'Envoy':<16}{'MCP backend'}")
    tags = {}
    for exchange in exchanges:
        tags[exchange.tag] = tags.get(exchange.tag, 0) + 1
    entries = {tag: envoy_entries(demo.args, tag, count) for tag, count in tags.items()}
    records = {tag: backend_records(demo.args, tag) for tag in tags}
    for number, exchange in enumerate(exchanges, 1):
        entry = (entries.get(exchange.tag) or [None])[0]
        received = records.get(exchange.tag)
        print(f"    {number:<3}{exchange.headers.get(MCP_METHOD_HEADER, '-'):<12}"
              f"{exchange.headers.get(MCP_NAME_HEADER, '-'):<20}"
              f"{exchange.headers.get(MCP_PROTOCOL_VERSION_HEADER, '-'):<22}"
              f"{exchange.headers.get('mcp-session-id', 'none'):<16}"
              f"{'forwarded' if forwarded(entry) else 'answered':<16}"
              f"{'received, ' + str(received[0].get('status')) if received else 'not received'}")
    print()
    print("    The _meta that each request carried in its body (request 1's):")
    for key, value in (exchanges[0].params.get("_meta", {}) if exchanges else {}).items():
        demo.detail(f"{key}: {json.dumps(value)}")
    print()

    def consistent(exchange):
        meta = exchange.params.get("_meta") or {}
        name_ok = (exchange.headers.get(MCP_NAME_HEADER) == exchange.params.get("name")
                   if exchange.body.get("method") == "tools/call" else True)
        return (exchange.headers.get(MCP_PROTOCOL_VERSION_HEADER) == PROTOCOL_VERSION
                and exchange.headers.get(MCP_METHOD_HEADER) == exchange.body.get("method")
                and name_ok and meta.get(PROTOCOL_VERSION_META_KEY) == PROTOCOL_VERSION
                and isinstance(meta.get(CLIENT_CAPABILITIES_META_KEY), dict)
                and meta.get(CLIENT_INFO_META_KEY) == CLIENT_INFO)

    methods = sorted({(exchange.body or {}).get("method") or "?" for exchange in exchanges})
    demo.check(
        bool(exchanges) and all(exchange.body and consistent(exchange) for exchange in exchanges),
        "every request carried MCP-Protocol-Version, Mcp-Method (and Mcp-Name for tools/call) "
        "matching its body, and a _meta with protocolVersion, clientInfo and clientCapabilities")
    demo.check(
        all(exchange.method == "POST" for exchange in exchanges)
        and not {"initialize", "notifications/initialized", "server/discover"} & set(methods),
        f"no handshake, probe, GET stream or DELETE: only POSTs of {methods}")
    demo.check(
        not any("mcp-session-id" in exchange.headers
                or "mcp-session-id" in exchange.response_headers for exchange in exchanges),
        "no Mcp-Session-Id in any request or response: no protocol session")
    demo.check(
        all(forwarded(entry) for tag in tags for entry in entries[tag])
        and all(len(entries[tag]) == count and len(records[tag]) == count
                for tag, count in tags.items()),
        "Envoy's MCP filter validated and forwarded each request, and the MCP backend received "
        "each one, on its own")


# 5. to 7. Raw HTTP requests that the SDK would not send


@dataclasses.dataclass
class Probe:
    """A raw HTTP request to Envoy's main listener, and what must happen to it."""
    name: str
    title: str
    headers: dict
    body: dict
    status: int
    # The JSON-RPC error code of the response, or None for a result.
    code: int | None = None
    # Whether Envoy forwards it to the MCP backend, rather than answering it itself.
    forwarded: bool = False
    # How much each MCP filter counter goes up.
    counters: dict = dataclasses.field(default_factory=dict)


def raw_headers(method=None, name=None, version=PROTOCOL_VERSION):
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


def raw_meta(version=PROTOCOL_VERSION, client_capabilities=True):
    meta = {PROTOCOL_VERSION_META_KEY: version, CLIENT_INFO_META_KEY: RAW_CLIENT_INFO}
    if client_capabilities:
        meta[CLIENT_CAPABILITIES_META_KEY] = {}
    return meta


def health_call(request_id, meta=None):
    """A tools/call of get_service_health for checkout."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "get_service_health",
            "arguments": {"service": "checkout"},
            "_meta": raw_meta() if meta is None else meta
        },
    }


def send(host, port, probe, tag):
    """Sends the probe's request. Returns the status and the body of the response."""
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        connection.request("POST", "/mcp", body=json.dumps(probe.body),
                           headers={**probe.headers, "x-e2e-case": tag})
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


def describe_body(body):
    params = body.get("params") or {}
    name = f" of {params['name']}" if "name" in params else ""
    meta = params.get("_meta")
    keys = ", ".join(f"{short_key(key)}={json.dumps(value)}" if key == PROTOCOL_VERSION_META_KEY
                     else short_key(key) for key, value in meta.items()) if meta else "none"
    return f"body: {body.get('method')}{name}; _meta: {keys}"


def run_probe(demo, probe):
    tag = f"demo-{probe.name}"
    demo.step(probe.title)
    status, text = send(demo.args.envoy_host, demo.args.port, probe, tag)
    try:
        message = json.loads(text)
    except ValueError:
        message = None
    if not isinstance(message, dict):
        message = {}
    error = message.get("error") or {}
    entry = (envoy_entries(demo.args, tag) or [None])[0]
    records = backend_records(demo.args, tag)

    print(f"      Request   POST /mcp  {mcp_headers(probe.headers)}")
    print(f"                {describe_body(probe.body)}")
    expected = (f"Envoy forwards it; the MCP backend answers HTTP {probe.status}" if probe.forwarded
                else f"Envoy rejects it itself: HTTP {probe.status}, JSON-RPC {probe.code}")
    print(f"      Expected  {expected}")
    if error:
        data = f", data {compact(error['data'], 80)}" if "data" in error else ""
        actual = f"HTTP {status}, JSON-RPC {error.get('code')} {error.get('message')!r}{data}"
    else:
        result = message.get("result") or {}
        actual = f"HTTP {status}, result {compact(result.get('structuredContent', result), 80)}"
    print(f"      Actual    {actual}")
    print(f"      Handled   {handled_by(entry)}")
    backend = (f"received it, and answered {records[0].get('status')}" if records else
               "did not receive it")
    print(f"      Backend   {backend}")
    ok = (status == probe.status and error.get("code") == probe.code
          and forwarded(entry) == probe.forwarded and bool(records) == probe.forwarded)
    for name, increase in probe.counters.items():
        demo.expected_counters[name] = demo.expected_counters.get(name, 0) + increase
    demo.check(ok, "as expected" if ok else "NOT as expected")


def header_validation(demo):
    demo.section("5. Header Validation (Envoy MCP filter)")
    print("    Raw HTTP requests, each a tools/call of get_service_health for checkout, with the "
          "MCP headers that 2026-07-28 requires, or not.")
    encoded = "=?base64?" + base64.b64encode(b"get_service_health").decode() + "?="
    mismatch = {"header_mismatch": 1}
    for probe in (
            Probe("valid-headers", "Valid Mcp-Method and Mcp-Name",
                  raw_headers("tools/call", "get_service_health"), health_call("valid-headers"),
                  200, forwarded=True),
            Probe("base64-mcp-name", f"Base64-encoded Mcp-Name: the filter decodes {encoded}",
                  raw_headers("tools/call", encoded), health_call("base64-mcp-name"), 200,
                  forwarded=True),
            Probe("mcp-method-mismatch", "Mcp-Method mismatch: header tools/list, body tools/call",
                  raw_headers("tools/list", "get_service_health"),
                  health_call("mcp-method-mismatch"), 400, HEADER_MISMATCH, counters=mismatch),
            Probe("mcp-name-mismatch",
                  "Mcp-Name mismatch: header get_incident, body get_service_health",
                  raw_headers("tools/call", "get_incident"), health_call("mcp-name-mismatch"),
                  400, HEADER_MISMATCH, counters=mismatch),
            Probe("missing-mcp-method", "Missing Mcp-Method header",
                  raw_headers(name="get_service_health"), health_call("missing-mcp-method"), 400,
                  HEADER_MISMATCH, counters=mismatch),
            Probe("missing-mcp-name", "Missing Mcp-Name header on a tools/call",
                  raw_headers("tools/call"), health_call("missing-mcp-name"), 400,
                  HEADER_MISMATCH, counters=mismatch),
    ):
        run_probe(demo, probe)


async def version_enforcement(demo):
    demo.section("6. Protocol Version Enforcement (Envoy MCP filter)")
    for probe in (
            Probe("unsupported-version", "Unsupported protocol version 2099-01-01",
                  raw_headers("tools/call", "get_service_health", version="2099-01-01"),
                  health_call("unsupported-version", raw_meta(version="2099-01-01")), 400,
                  UNSUPPORTED_PROTOCOL_VERSION),
            Probe("version-mismatch",
                  "MCP-Protocol-Version 2026-07-28, but protocolVersion 2025-11-25 in _meta",
                  raw_headers("tools/call", "get_service_health"),
                  health_call("version-mismatch", raw_meta(version="2025-11-25")), 400,
                  HEADER_MISMATCH, counters={"header_mismatch": 1}),
    ):
        run_probe(demo, probe)

    demo.step(f"The SDK client, through the listener whose MCP filter supports versions up to "
              f"{CAPPED_MAX_VERSION} only")
    tag = demo.recorder.tag = "demo-sdk-capped-listener"
    url = f"http://{demo.args.envoy_host}:{demo.args.capped_port}/mcp"
    http_client, client = demo.sdk_client(url, cache=None)
    error = None
    async with http_client, client:
        try:
            await client.list_tools()
        except MCPError as caught:
            error = caught
    exchange = (demo.recorder.tagged(tag) or [None])[0]
    if exchange is not None:
        demo.say("SDK client", f"POST /mcp  {mcp_headers(exchange.headers)} -> HTTP "
                 f"{exchange.status}")
    demo.say("SDK client", f"list_tools() raised MCPError {error.code} {error.message!r}, data "
             f"{compact(error.data, 90)}" if error else "list_tools() raised no error")
    entries, records = show_tagged_path(demo, tag)
    supported = [version for version in ENVOY_PROTOCOL_VERSIONS if version <= CAPPED_MAX_VERSION]
    demo.check(
        error is not None and error.code == UNSUPPORTED_PROTOCOL_VERSION
        and (error.data or {}).get("supported") == supported and not records
        and entries and not forwarded(entries[0]),
        f"Envoy rejected it with -32022, naming the versions it supports, {supported}; the SDK "
        "client raised it as an MCPError, and did not fall back to the legacy handshake")


def client_capabilities(demo):
    demo.section("7. Client Capabilities Validation (Envoy MCP filter)")
    print("    At 2026-07-28 every request must carry io.modelcontextprotocol/clientCapabilities "
          "in params._meta. The filter checks that the key is there.")
    for probe in (
            Probe("missing-client-capabilities", "_meta without clientCapabilities",
                  raw_headers("tools/call", "get_service_health"),
                  health_call("missing-client-capabilities", raw_meta(client_capabilities=False)),
                  400, INVALID_PARAMS),
            Probe("with-client-capabilities", "The same request, with clientCapabilities: {}",
                  raw_headers("tools/call", "get_service_health"),
                  health_call("with-client-capabilities"), 200, forwarded=True),
    ):
        run_probe(demo, probe)


# 8. Optional Advanced Features: implemented by the SDK client and server; Envoy forwards them


async def server_discover(demo, client):
    demo.step("server/discover: the MCP backend describes itself")
    tag = demo.recorder.tag = "demo-sdk-server-discover"
    discovered = await client.session.send_discover(PROTOCOL_VERSION)
    server_info = (discovered.get("_meta") or {}).get("io.modelcontextprotocol/serverInfo")
    demo.say("SDK client", f"session.send_discover({PROTOCOL_VERSION!r})")
    demo.say("MCP backend", f"supportedVersions {discovered.get('supportedVersions')}, serverInfo "
             f"{compact(server_info)}")
    demo.say("MCP backend", f"capabilities {compact(discovered.get('capabilities'))}")
    demo.say("MCP backend", f"ttlMs {discovered.get('ttlMs')}, cacheScope "
             f"{discovered.get('cacheScope')}, resultType {discovered.get('resultType')}")
    demo.detail(f"instructions: {discovered.get('instructions')}")
    entries, records = show_tagged_path(demo, tag)
    demo.check(
        PROTOCOL_VERSION in (discovered.get("supportedVersions") or []) and entries
        and forwarded(entries[0]) and entries[0].get("mcp_method") == "server/discover"
        and len(records) == 1,
        "the MCP backend answered server/discover; Envoy's MCP filter validated it like any other "
        "request, and forwarded it")


async def cache_hints(demo, client):
    demo.step("Cache hints: ttlMs and cacheScope on the tools/list result")
    first = (demo.recorder.tagged("demo-sdk-tools-list") or [None])[0]
    hint = (first.result.get("ttlMs"), first.result.get("cacheScope")) if first else (None, None)
    demo.say("MCP backend", f"section 2's tools/list result carried ttlMs {hint[0]} and "
             f"cacheScope {hint[1]}; Envoy's MCP filter does not touch responses")

    tag = demo.recorder.tag = "demo-sdk-tools-list-cached"
    listed = await client.list_tools()
    cached = demo.recorder.tagged(tag)
    demo.say("SDK client", f"list_tools() -> {len(listed.tools)} tools, with {len(cached)} HTTP "
             "requests: " + ("served from the SDK client's own cache" if not cached else
                             "not served from the cache"))
    demo.check(hint[0] is not None and hint[0] > 0 and not cached,
               "the SDK client honored the MCP backend's hint: no request reached Envoy")

    tag = demo.recorder.tag = "demo-sdk-tools-list-bypass"
    await client.list_tools(cache_mode="bypass")
    sent = demo.recorder.tagged(tag)
    demo.say("SDK client", f"list_tools(cache_mode='bypass') -> {len(sent)} HTTP request")
    entries, records = show_tagged_path(demo, tag)
    demo.check(len(sent) == 1 and entries and forwarded(entries[0]) and len(records) == 1,
               "bypassing the cache, the request went through Envoy to the MCP backend again")


async def multi_round_trip(demo, client, service, incident_id):
    demo.step(f"Multi round-trip request: apply_remediation({service!r}, {incident_id!r}) needs "
              "the operator's approval")
    tag = demo.recorder.tag = "demo-sdk-apply-remediation"
    result = await client.call_tool("apply_remediation",
                                    {"service": service, "incident_id": incident_id})
    rounds = demo.recorder.tagged(tag)
    first, second = (rounds + [None, None])[:2]
    if first is not None:
        requests = first.result.get("inputRequests") or {}
        demo.say("SDK client", f"round 1: tools/call of apply_remediation -> HTTP {first.status}")
        demo.say("MCP backend", f"resultType {first.result.get('resultType')}: "
                 f"{len(requests)} input request(s), and a sealed requestState of "
                 f"{len(first.result.get('requestState') or '')} characters")
        for key, request in requests.items():
            demo.detail(f"{key}: {request.get('method')}: "
                        f"{(request.get('params') or {}).get('message')!r}")
    for params in demo.elicitations:
        demo.say("SDK client", f"elicitation callback, given {params.message!r}: answered accept, "
                 f"{json.dumps(APPROVAL)}")
    if second is not None:
        demo.say("SDK client", f"round 2: tools/call again, with inputResponses "
                 f"{compact(second.params.get('inputResponses'), 70)} and the requestState -> "
                 f"HTTP {second.status}")
        demo.say("MCP backend", f"resultType {second.result.get('resultType')}: "
                 f"{compact(second.result.get('structuredContent'))}")
    entries, records = show_tagged_path(demo, tag, count=2)
    demo.check(
        first is not None and second is not None
        and first.result.get("resultType") == "input_required"
        and second.params.get("requestState") == first.result.get("requestState")
        and "inputResponses" in second.params and not result.is_error
        and (result.structured_content or {}).get("approved_by") == APPROVAL["operator"],
        "the SDK server asked for input, the SDK client answered it, and the call completed in a "
        "second round")
    demo.check(
        len(entries) == 2 and all(forwarded(entry) for entry in entries) and len(records) == 2,
        "Envoy forwarded both rounds as ordinary tools/call requests: the MCP filter does not "
        "implement multi round-trip requests, and needs not")


async def advanced(demo, client, scenario):
    demo.section("8. Optional Advanced Features (SDK client and MCP backend; Envoy forwards)")
    await server_discover(demo, client)
    await cache_hints(demo, client)
    if scenario is None:
        demo.check(False, "the multi round-trip request needs section 3's incident")
        return
    await multi_round_trip(demo, client, *scenario)


# 9. Final Summary


def summary(demo, counters_before):
    demo.section("9. Final Summary")
    sections = []
    for section, _, _ in demo.results:
        if section not in sections:
            sections.append(section)
    for section in sections:
        results = [ok for name, _, ok in demo.results if name == section]
        mark = demo.style.paint("32", "✓") if all(results) else demo.style.paint("31", "✗")
        print(f"    {mark} {section}: {sum(results)} of {len(results)} checks passed")

    entries = [entry for entry in read_json_lines(demo.args.run_dir / "access.log")
               if str(entry.get("e2e_case") or "").startswith("demo-")]
    answered = sum(not forwarded(entry) for entry in entries)
    print()
    print(f"    Envoy logged {len(entries)} demo requests: it forwarded "
          f"{len(entries) - answered} to the MCP backend, and answered {answered} itself.")
    try:
        after = {prefix: mcp_counters(demo.args, prefix) for prefix in counters_before}
    except OSError as error:
        demo.check(False, f"read the MCP filter counters from Envoy's admin endpoint: {error}")
        after = {}
    for prefix, before in counters_before.items():
        if prefix not in after:
            continue
        if None in before.values() or None in after[prefix].values():
            demo.check(False, f"the MCP filter counters of {prefix} are in Envoy's stats")
            continue
        changes = {name: after[prefix][name] - before[name] for name in before}
        expected = demo.expected_counters if prefix == MAIN_STAT_PREFIX else {}
        wanted = {name: expected.get(name, 0) for name in before}
        demo.check(changes == wanted, f"MCP filter counters of {prefix}: "
                   f"{describe_changes(changes)} (expected {describe_changes(wanted)})")
    print()
    print("    Who does what in this demo:")
    print("      SDK client        adopts 2026-07-28 without a handshake; puts "
          "MCP-Protocol-Version, Mcp-Method, Mcp-Name and _meta on every request; caches "
          "tools/list as hinted; answers input requests through its elicitation callback")
    print("      Envoy MCP filter  checks each request's MCP headers against its body, its "
          "protocol version and its clientCapabilities; rejects invalid requests itself; "
          "forwards the rest; does not cache, discover, or drive input requests")
    print("      MCP backend       runs the tools; answers server/discover; sets the cache hints; "
          "asks for input with resultType input_required; keeps no session")
    print()
    print(f"    Detailed logs in {demo.args.run_dir}: access.log (Envoy, one JSON object per "
          "request, by X-E2E-Case), backend_requests.jsonl, envoy.log, backend.log, stats.txt")
    passed = sum(ok for _, _, ok in demo.results)
    print()
    print(demo.style.paint("1", f"    Demo checks: {passed} of {len(demo.results)} passed"))
    for section, text, ok in demo.results:
        if not ok:
            print(f"    Failed: {section}: {text}")


async def run(demo):
    url = f"http://{demo.args.envoy_host}:{demo.args.port}/mcp"
    http_client, client = demo.sdk_client(url, elicitation_callback=demo.approve)
    async with http_client, client:
        await connection(demo, client, url)
        await tool_discovery(demo, client)
        scenario = await multi_step(demo, client)
        stateless_metadata(demo)
        header_validation(demo)
        await version_enforcement(demo)
        client_capabilities(demo)
        await advanced(demo, client, scenario)


def main():
    # The SDK's HTTP client logs every request at INFO; the demo prints its own account of them.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    demo = Demo(parse_args())
    print(f"MCP {PROTOCOL_VERSION} developer demo: MCP Python SDK "
          f"{importlib.metadata.version('mcp')} -> Envoy {demo.args.envoy_host}:{demo.args.port} "
          f"-> MCP backend {demo.args.backend_host}:{demo.args.backend_port}")
    counters_before = None
    try:
        counters_before = {prefix: mcp_counters(demo.args, prefix)
                           for prefix in (MAIN_STAT_PREFIX, CAPPED_STAT_PREFIX)}
        anyio.run(run, demo)
    # Whatever went wrong, in the SDK, Envoy or the server, is a failed check.
    except Exception as error:
        while getattr(error, "exceptions", None):
            error = error.exceptions[0]
        demo.check(False, f"the demo did not finish: {type(error).__name__}: {error}")
    if counters_before is not None:
        summary(demo, counters_before)
    try:
        text, _ = read_stats(demo.args)
        (demo.args.run_dir / "stats.txt").write_text(text)
    except OSError as error:
        print(f"Could not save Envoy's stats in stats.txt: {error}")
    sys.exit(0 if all(ok for _, _, ok in demo.results) else 1)


if __name__ == "__main__":
    main()
