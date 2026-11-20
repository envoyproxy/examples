"""What the MCP JSON-REST bridge end-to-end test checks against, and the gaps that it knows of.

Each check of rest_cases.py cites one of REQUIREMENTS: what the specification, or the bridge's API
docs, require, at what level, and where. The specification is MCP 2026-07-28, from
https://github.com/modelcontextprotocol/modelcontextprotocol (docs/specification/2026-07-28 and
schema/2026-07-28). Line numbers are those of the .mdx files there. The bridge's API docs are
api/envoy/extensions/filters/http/mcp_json_rest_bridge/v3/mcp_json_rest_bridge.proto, at Envoy
commit 867b47e0e5. Where the API docs say nothing about a behavior, a CONTRACT requirement cites the
implementation (a function of a .cc file) or the change that introduced it.

A check that also names one of KNOWN_GAPS is a compliance check: it fails on the current Envoy, for
that reason, and the client reports it as a known gap instead of a regression. When such a check
passes, the gap is fixed: remove the gap from the check, so that it guards against a regression
from then on.
"""
import dataclasses

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
    "JSONRPC-ECHO-ID": R(
        "MUST", "A response has the id of the request that it answers.",
        "basic/index §Responses (L70, L103)"),
    "JSONRPC-PARSE": R(
        "MUST", "A body that is not JSON is a parse error: -32700.", "JSON-RPC 2.0 §5.1"),
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
    # The Streamable HTTP transport.
    "HTTP-JSON-RESPONSE": R(
        "MUST", "A request gets Content-Type application/json (or text/event-stream), with a "
        "JSON-RPC response.", "streamable-http §Sending Messages (L88-91)"),
    # Mcp-Param headers (x-mcp-header).
    "PARAM-MATCH": R(
        "MUST", "An Mcp-Param-{Name} header equals the argument after Base64 decoding: a missing "
        "header for a present argument, a different value, or invalid characters get 400 and "
        "-32020.", "streamable-http §Server Behavior for Custom Headers (L552-566)"),
    "PARAM-FORWARD": R(
        "CONTRACT", "Mcp-Param headers are never added, removed or modified: the REST backend gets "
        "them as sent.", PROTO + " McpParamHeader"),
    # The bridge's API docs.
    "BRIDGE-LOCAL-LIST": R(
        "CONTRACT", "tool_list_local answers tools/list itself, from each tool's name and "
        "tool_list_config: title, description, and input_schema, {\"type\":\"object\"} if none.",
        PROTO + " ServerToolConfig.tool_list_local, ToolsListSpecificConfig"),
    "BRIDGE-HTTP-LIST": R(
        "CONTRACT", "tool_list_http_rule transcodes tools/list to the rule's GET, and answers with "
        "the backend's ListToolsResult.", PROTO + " ServerToolConfig.tool_list_http_rule"),
    "BRIDGE-QUERY": R(
        "CONTRACT", "Arguments not in the path or the body become query parameters.",
        PROTO + " HttpRule (mapping rule 3)"),
    "BRIDGE-BODY": R(
        "CONTRACT", "body \"*\" sends the arguments that are not in the path; no body sends none.",
        PROTO + " HttpRule.body"),
    "BRIDGE-RESPONSE": R(
        "CONTRACT", "A REST response becomes a tools/call result whose text content is the body, "
        "with isError for a status >= 400.", "mcp_json_rest_bridge_filter.cc (encodeJsonRpcData)"),
    "BRIDGE-STREAMING": R(
        "CONTRACT", "With text_content_streaming_enabled, the body is streamed as text content.",
        PROTO + " ToolConfig.text_content_streaming_enabled"),
    "BRIDGE-EMPTY-BODY": R(
        "CONTRACT", "A POST with an empty body is answered at once, as a body that is not JSON: "
        "HTTP 400 and -32700.",
        "mcp_json_rest_bridge_filter.cc decodeHeaders (envoyproxy/envoy#48635)"),
    # Compatibility with the official MCP Python SDK, at the version that the suite pins.
    "SDK-CALL": R(
        "SDK", "The MCP Python SDK calls a tool and gets its result.",
        "mcp==2.2.0 ClientSession.send_request, CallToolResult"),
}

KNOWN_GAPS = {
    "G2": Gap(
        "tools/list from the REST backend is passed through as is",
        "tool_list_http_rule answers a 2026-07-28 tools/list with the backend's ListToolsResult "
        "verbatim (encodeJsonRpcData, ToolsList). A backend that follows the API docs' reference "
        "schema, 2025-11-25, has no resultType, ttlMs or cacheScope, so the result has none."),
    "G12": Gap(
        "Results have no serverInfo",
        "Only server/discover's result has _meta io.modelcontextprotocol/serverInfo."),
}
