"""What the MCP JSON-REST bridge end-to-end test checks against, and the gaps that it knows of.

Each check of rest_cases.py cites one of REQUIREMENTS: what the specification, or the bridge's API
docs, require, at what level, and where. The specification is MCP 2026-07-28, from
https://github.com/modelcontextprotocol/modelcontextprotocol (docs/specification/2026-07-28 and
schema/2026-07-28), and 2025-11-25 for the legacy (initialize-based) requests that the bridge still
serves. Line numbers are those of the .mdx files there. The bridge's API docs are
api/envoy/extensions/filters/http/mcp_json_rest_bridge/v3/mcp_json_rest_bridge.proto, with line
numbers at Envoy commit 867b47e0e5. Where the API docs say nothing about a behavior, a CONTRACT
requirement cites the implementation (a function of a .cc file) or the change that introduced it.

A check that also names one of KNOWN_GAPS is a compliance check: it fails on the current Envoy, for
that reason, and the client reports it as a known gap instead of a regression. When such a check
passes, the gap is fixed: remove the gap from the check, so that it guards against a regression
from then on.

A check that names one of DIAGNOSTICS is a diagnostic check: it records how the bridge alone
(listener B) behaves where the filter in front of it in the supported chain (listener C) meets the
requirement, which regression checks on listener C verify. The client reports it, with its
evidence, but it is neither a regression nor an endpoint compliance failure, and it never fails the
run. See README.md.
"""
import dataclasses

SPEC = "https://modelcontextprotocol.io/specification/2026-07-28"
PROTO = "mcp_json_rest_bridge.proto"


@dataclasses.dataclass(frozen=True)
class Requirement:
    level: str  # MUST, SHOULD, CONTRACT (the bridge's API docs), or SDK (client compatibility)
    text: str
    source: str


@dataclasses.dataclass(frozen=True)
class Gap:
    title: str
    detail: str


R = Requirement
REQUIREMENTS = {
    # JSON-RPC.
    "JSONRPC-VERSION": R(
        "MUST", "A request whose jsonrpc member is not exactly \"2.0\" is an invalid request: "
        "JSON-RPC error -32600.", "JSON-RPC 2.0 §4, §5.1; basic/index §Messages (L27-29)"),
    "JSONRPC-METHOD": R(
        "MUST", "A request without a string method is an invalid request: -32600.",
        "JSON-RPC 2.0 §4, §5.1"),
    "JSONRPC-ID": R(
        "MUST", "A request id is a string or an integer, never null: a request with any other id "
        "is an invalid request, -32600.", "basic/index §Requests (L46-47); JSON-RPC 2.0 §5.1"),
    "JSONRPC-ECHO-ID": R(
        "MUST", "A response has the id of the request that it answers.",
        "basic/index §Responses (L70, L103)"),
    "JSONRPC-NO-ID": R(
        "MUST", "An error response to a message whose id could not be read has no id member: the "
        "2026-07-28 schema allows a string or integer id only, not null.",
        "schema.json JSONRPCErrorResponse (id: RequestId, optional); streamable-http §Sending "
        "Messages (L85-87)"),
    "JSONRPC-PARSE": R(
        "MUST", "A body that is not JSON is a parse error: -32700.", "JSON-RPC 2.0 §5.1"),
    "JSONRPC-SINGLE": R(
        "MUST", "A POST body is a single JSON-RPC request or notification: a batch (a JSON array) "
        "is an invalid request, -32600.", "streamable-http §Sending Messages (L80-81); JSON-RPC "
        "2.0 §5.1"),
    # Results.
    "RESULT-TYPE": R(
        "MUST", "Every result of a 2026-07-28 request has resultType, \"complete\" for a final "
        "result.", "basic/index §Result Responses (L73, L81); schema Result"),
    "CACHE-HINTS": R(
        "MUST", "A complete result of server/discover or tools/list has ttlMs, an integer >= 0, "
        "and cacheScope, \"public\" or \"private\".",
        "server/utilities/caching §Cacheable Results (L13-21, L60); schema CacheableResult"),
    "RESULT-SCHEMA": R(
        "MUST", "A result matches the 2026-07-28 schema of its method (checked with the MCP SDK's "
        "schema models, mcp_types).", "basic/index §Schema (L236-245)"),
    "SERVER-INFO": R(
        "SHOULD", "Every result's _meta has io.modelcontextprotocol/serverInfo.",
        "basic/index §Per-response protocol fields (L396-402)"),
    "META-REQUIRED": R(
        "MUST", "A 2026-07-28 request whose params._meta lacks io.modelcontextprotocol/"
        "protocolVersion or io.modelcontextprotocol/clientCapabilities is malformed: -32602, with "
        "HTTP 400.", "basic/index §Per-request protocol fields (L373-382)"),
    # The Streamable HTTP transport.
    "HTTP-NOTIFICATION": R(
        "MUST", "A notification gets 202 with no body if the server accepts it, and otherwise an "
        "HTTP error status, with at most a JSON-RPC error response that has no id; never a 2xx "
        "JSON-RPC response.", "streamable-http §Sending Messages (L82-87); basic/index "
        "§Notifications (L160)"),
    "HTTP-JSON-RESPONSE": R(
        "MUST", "A request gets Content-Type application/json (or text/event-stream), with a "
        "JSON-RPC response.", "streamable-http §Sending Messages (L88-91)"),
    "HTTP-VERSION-HEADER": R(
        "MUST", "MCP-Protocol-Version is required and equals params._meta io.modelcontextprotocol/"
        "protocolVersion: a missing, duplicated or different one gets 400 and -32020 "
        "(HeaderMismatch).", "streamable-http §Protocol Version Header (L252-261), §Server "
        "Validation (L597-631)"),
    "HTTP-UNSUPPORTED-VERSION": R(
        "MUST", "A protocol version that the server does not implement gets 400 and -32022 "
        "(UnsupportedProtocolVersion), whose data lists the supported versions and the requested "
        "one.", "streamable-http (L263-269); versioning §Protocol Version Negotiation (L48-67); "
        "schema UnsupportedProtocolVersionError"),
    "HTTP-METHOD-NOT-FOUND": R(
        "MUST", "An RPC method that the server does not implement gets 404 and -32601.",
        "streamable-http §Protocol Version Header (L271-275)"),
    "HTTP-STANDARD-HEADERS": R(
        "MUST", "Mcp-Method (every request) and Mcp-Name (tools/call) are required and equal "
        "method and params.name: missing, duplicated or different ones get 400 and -32020.",
        "streamable-http §Standard Request Headers (L288-293), §Server Validation (L622-631)"),
    "HTTP-BASE64": R(
        "MUST", "The server decodes =?base64?...?= header values before comparing them with the "
        "body, and rejects values that do not decode: 400 and -32020.",
        "streamable-http §Value Encoding (L498-504), §Server Validation (L622-631)"),
    "HTTP-CASE": R(
        "MUST", "Header names are compared case-insensitively, and header values "
        "case-sensitively.", "streamable-http §Case Sensitivity (L570-576)"),
    "HTTP-405": R(
        "SHOULD", "GET and DELETE to the MCP endpoint get 405 Method Not Allowed.",
        "streamable-http §Earlier Streamable HTTP Revisions (L683-684)"),
    "HTTP-SESSION": R(
        "SHOULD", "An Mcp-Session-Id header is ignored: no session id is minted or echoed.",
        "streamable-http §Earlier Streamable HTTP Revisions (L685-686)"),
    "HTTP-FRAMING": R(
        "MUST", "Every response is a complete HTTP/1.1 message: its body has the length that its "
        "Content-Length says, and it arrives without the client having to time out.",
        "RFC 9112 §6 (message body length)"),
    "HTTP-ANSWERED": R(
        "MUST", "A POST is answered: a body that is not a JSON-RPC message gets an error response "
        "(-32700 or -32600), not silence.", "JSON-RPC 2.0 §5; streamable-http §Sending Messages "
        "(L80-91)"),
    # Mcp-Param headers (x-mcp-header).
    "PARAM-MATCH": R(
        "MUST", "An Mcp-Param-{Name} header equals the argument after Base64 decoding: a missing "
        "header for a present argument, a different value, or invalid characters get 400 and "
        "-32020.", "streamable-http §Server Behavior for Custom Headers (L552-566)"),
    "PARAM-ABSENT": R(
        "MUST", "No Mcp-Param header is expected for an argument that is null or absent.",
        "streamable-http §Server Behavior for Custom Headers (L563-565)"),
    "PARAM-UNEXPECTED": R(
        "MUST", "An Mcp-Param header whose argument is absent does not match the body: 400 and "
        "-32020.", "streamable-http §Server Validation (L582-587); " + PROTO + " McpParamHeader"),
    "PARAM-INTEGER": R(
        "SHOULD", "Integer values are compared numerically: \"3.0\" matches 3.",
        "streamable-http §Server Validation (L591-593)"),
    "PARAM-DUPLICATE": R(
        "CONTRACT", "A duplicated Mcp-Param header is rejected: 400 and -32020.",
        PROTO + " McpParamHeader"),
    "PARAM-SCOPE": R(
        "CONTRACT", "Mcp-Param headers are validated for 2026-07-28 requests only.",
        PROTO + " ToolConfig.mcp_param_headers"),
    "PARAM-FORWARD": R(
        "CONTRACT", "Mcp-Param headers are never added, removed or modified: the REST backend gets "
        "them as sent.", PROTO + " McpParamHeader"),
    # Versioning and the stateless lifecycle.
    "VER-DISCOVER": R(
        "MUST", "server/discover is implemented: a DiscoverResult whose supportedVersions include "
        "2026-07-28, with the server's capabilities.", "versioning (L73-78); server/discover; "
        "schema DiscoverResult"),
    "VER-MODERN": R(
        "MUST", "A request with 2026-07-28 params._meta is served under 2026-07-28, which has no "
        "initialize or notifications/initialized.", "versioning §Backward Compatibility "
        "(L174-177); changelog §Major changes 2"),
    "TOOLS-CAPABILITY": R(
        "MUST", "A server that has tools declares the tools capability.", "server/tools "
        "§Capabilities (L47)"),
    "STATELESS": R(
        "MUST", "Every request is served on its own, with no handshake or prior request.",
        "basic/index §Statelessness (L184-193)"),
    "LEGACY-VERSION-400": R(
        "MUST", "A legacy request (no 2026-07-28 params._meta) with an invalid or unsupported "
        "MCP-Protocol-Version gets 400 Bad Request.", "2025-11-25 transports §Protocol Version "
        "Header (L279-280)"),
    "LEGACY-DEFAULT": R(
        "SHOULD", "A legacy request without MCP-Protocol-Version is served as 2025-03-26.",
        "2025-11-25 transports §Protocol Version Header (L274-277); " + PROTO +
        " fallback_protocol_version"),
    "LEGACY-INITIALIZE": R(
        "MUST", "initialize gets the requested version if the server supports it, and otherwise "
        "another one that it supports, with its capabilities and serverInfo.",
        "2025-11-25 lifecycle §Version Negotiation (L167-172), §Initialization (L98)"),
    "LEGACY-INITIALIZED": R(
        "MUST", "notifications/initialized is accepted: 202 with no body.",
        "2025-11-25 transports §Sending Messages (L94-100)"),
    # Tools.
    "TOOLS-ORDER": R(
        "SHOULD", "tools/list returns the tools in a deterministic order.",
        "server/tools §Capabilities (L71)"),
    "TOOLS-PROTOCOL-ERROR": R(
        "MUST", "An unknown tool, or a tools/call that fails the CallToolRequest schema, gets a "
        "JSON-RPC error, -32602.", "server/tools §Error Handling (L742-758)"),
    "TOOLS-EXECUTION-ERROR": R(
        "SHOULD", "An error of the tool, an API failure or an input validation error such as a "
        "missing or invalid argument, is a result with isError: true, not a protocol error.",
        "server/tools §Error Handling (L760-785); schema CallToolResult.isError; SEP-1303"),
    "PAGE-CURSOR": R(
        "SHOULD", "An invalid cursor gets -32602.", "server/utilities/pagination (L111)"),
    "ERROR-CODE-RANGE": R(
        "SHOULD", "A new implementation does not use the legacy error codes -32000 to -32019.",
        "basic/index §Error Codes (L117-121)"),
    # The bridge's API docs.
    "BRIDGE-LOCAL-LIST": R(
        "CONTRACT", "tool_list_local answers tools/list itself, from each tool's name and "
        "tool_list_config: title, description, and input_schema, {\"type\":\"object\"} if none.",
        PROTO + " ServerToolConfig.tool_list_local, ToolsListSpecificConfig"),
    "BRIDGE-HTTP-LIST": R(
        "CONTRACT", "tool_list_http_rule transcodes tools/list to the rule's GET, and answers with "
        "the backend's ListToolsResult.", PROTO + " ServerToolConfig.tool_list_http_rule"),
    "BRIDGE-PATH": R(
        "CONTRACT", "Path template variables take argument values: {var} fills one segment, with "
        "its / encoded; {var=pattern} may span segments.", PROTO + " HttpRule"),
    "BRIDGE-QUERY": R(
        "CONTRACT", "Arguments not in the path, the body or a binding become query parameters: "
        "nested fields with dotted names, arrays repeated.", PROTO + " HttpRule (mapping rule 3)"),
    "BRIDGE-BODY": R(
        "CONTRACT", "body \"*\" sends the arguments that are not in the path; body \"field\" sends "
        "that field, which is required; no body sends none.", PROTO + " HttpRule.body"),
    "BRIDGE-BINDINGS": R(
        "CONTRACT", "Header and cookie bindings send arguments as headers and cookies, not as "
        "query parameters.", PROTO + " HttpRule.ParameterBinding"),
    "BRIDGE-METHOD": R(
        "CONTRACT", "When several methods are set, the one with the highest field number is the "
        "effective one: get < put < post < delete < patch.", PROTO + " HttpRule (L464-466)"),
    "BRIDGE-RESPONSE": R(
        "CONTRACT", "A REST response becomes a tools/call result whose text content is the body, "
        "with isError for a status >= 400; HTTP 401 and 403 keep their status (MCP authorization).",
        "mcp_json_rest_bridge_filter.cc (encodeJsonRpcData); basic/authorization"),
    "BRIDGE-STREAMING": R(
        "CONTRACT", "With text_content_streaming_enabled, the body is streamed as text content, "
        "and each server-sent event is its own text item.",
        PROTO + " ToolConfig.text_content_streaming_enabled"),
    "BRIDGE-REQUEST-LIMIT": R(
        "CONTRACT", "A body over max_request_body_size (64 KiB by default) gets 413.",
        PROTO + " max_request_body_size"),
    "BRIDGE-RESPONSE-LIMIT": R(
        "CONTRACT", "A REST response over max_response_body_size (1 MiB by default) gets an error.",
        PROTO + " max_response_body_size"),
    "BRIDGE-TRACE": R(
        "CONTRACT", "trace_context_extraction moves traceparent from params._meta to the REST "
        "request's headers.", PROTO + " trace_context_extraction"),
    "BRIDGE-DISCOVER-CACHE": R(
        "CONTRACT", "server/discover's ttlMs and cacheScope are server_discovery_cache_config's.",
        PROTO + " ServerInfo.server_discovery_cache_config"),
    "BRIDGE-HEADER-FIRST": R(
        "CONTRACT", "A 2026-07-28 request with both a header error and an unsupported method gets "
        "400, not 404.", PROTO + " ServerInfo.max_supported_protocol_version"),
    "BRIDGE-MCP-FILTER": R(
        "CONTRACT", "With the MCP filter in front (REJECT_NO_MCP), a 2026-07-28 request without "
        "client capabilities gets 400 and -32602, and does not reach the backend.",
        PROTO + " ServerInfo.max_supported_protocol_version (L205-208); mcp_filter.cc "
        "completeParsing (envoyproxy/envoy#47915)"),
    "MCP-FILTER-JSONRPC": R(
        "CONTRACT", "With traffic_mode REJECT_NO_MCP, the MCP filter rejects a POST whose body is "
        "not a JSON-RPC 2.0 message (jsonrpc missing, or not \"2.0\") with HTTP 400, so that it "
        "reaches neither the bridge nor the REST backend.",
        "mcp.proto Mcp.TrafficMode.REJECT_NO_MCP (\"POST requests with JSON-RPC 2.0 messages\"); "
        "mcp_filter.cc completeParsing"),
    "BRIDGE-TRAVERSAL": R(
        "CONTRACT", "A path template value with a . or .. segment is never sent to the REST "
        "backend.", "http_request_builder.cc (envoyproxy/envoy#45931)"),
    # Compatibility with the official MCP Python SDK, at the version that the suite pins.
    "SDK-LIST": R("SDK", "The MCP Python SDK lists the tools.", "mcp==2.2.0 Client.list_tools"),
    "SDK-CALL": R(
        "SDK", "The MCP Python SDK calls a tool and gets its result.",
        "mcp==2.2.0 Client.call_tool"),
    "SDK-ERROR": R(
        "SDK", "The MCP Python SDK surfaces a JSON-RPC error as an MCPError with its code.",
        "mcp==2.2.0"),
    "SDK-DISCOVER": R(
        "SDK", "The MCP Python SDK negotiates 2026-07-28 with server/discover.",
        "mcp==2.2.0 Client(mode=\"auto\"), ClientSession.send_discover"),
    "SDK-PARAM": R(
        "SDK", "Mcp-Param headers as the MCP Python SDK encodes them from the tool's x-mcp-header "
        "annotations are accepted.", "mcp==2.2.0 mcp.shared.inbound"),
}

KNOWN_GAPS = {
    "G2": Gap(
        "tools/list from the REST backend is passed through as is",
        "tool_list_http_rule answers a 2026-07-28 tools/list with the backend's ListToolsResult "
        "verbatim (encodeJsonRpcData, ToolsList). A backend that follows the API docs' reference "
        "schema, 2025-11-25, has no resultType, ttlMs or cacheScope, so the result has none."),
    "G6": Gap(
        "Unsupported legacy versions get HTTP 200",
        "A request without a 2026-07-28 params._meta version is a legacy one; when its "
        "MCP-Protocol-Version is not a legacy version, the bridge answers -32602 \"Unsupported MCP "
        "version\" with HTTP 200 (validateMcpProtocolVersionHeader), not 400."),
    "G7": Gap(
        "Notifications get a JSON-RPC error with HTTP 200",
        "A message without an id, other than notifications/initialized, gets -32600 \"Missing ID "
        "field\" with HTTP 200 (validateJsonRpcIdAndMethod): neither 202 nor an HTTP error "
        "status."),
    "G8": Gap(
        "Errors for unreadable ids have \"id\": null",
        "When the request id could not be read, the bridge's error response has \"id\": null "
        "(encodeJsonRpcData, OperationFailed) instead of no id."),
    "G10": Gap(
        "Input validation errors are protocol errors",
        "A missing or invalid argument (path template variable, body field, header or cookie "
        "value, path traversal) gets JSON-RPC error -32602 (mapMcpToolToApiBackend, "
        "buildHttpRequest), not a tools/call result with isError: true."),
    "G11": Gap(
        "HttpRule method precedence differs from the API docs",
        "buildHttpRequest takes the first method set in the order get, put, post, delete, patch; "
        "the API docs say the one with the highest field number wins."),
    "G12": Gap(
        "Results have no serverInfo",
        "Only server/discover's result has _meta io.modelcontextprotocol/serverInfo."),
    "G13": Gap(
        "Legacy error code -32000",
        "Request too large, response too large and tools/list backend errors use -32000, from the "
        "legacy range."),
    "G14": Gap(
        "tools/list ignores an invalid cursor",
        "tools/list with a cursor that the server never issued gets the full list, not -32602."),
}

# How the bridge alone (listener B) behaves where the filter in front of it in the supported chain
# (listener C) meets the requirement: diagnostic, not endpoint compliance. G9 was a known gap until
# it was found that the MCP filter rejects these requests in the supported chain.
DIAGNOSTICS = {
    "G9": Gap(
        "The bridge alone does not check jsonrpc",
        "validateJsonRpcIdAndMethod checks method and id only, so the bridge alone serves a "
        "request without \"jsonrpc\": \"2.0\". In the supported chain, the MCP filter in "
        "REJECT_NO_MCP mode rejects such a request with HTTP 400 before the bridge (mcp_filter.cc "
        "completeParsing), "
        "as the regression checks of errors.jsonrpc-missing@C and errors.jsonrpc-version@C "
        "verify."),
}
