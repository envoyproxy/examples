#!/bin/bash -e

export NAME=mcp

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

# Sends an MCP request at protocol version 2026-07-28: mcp METHOD [TOOL [ARGUMENTS [CURL_ARGS...]]].
# The MCP filter requires the Mcp-Method header, and Mcp-Name for tools/call, to match the body, and
# params._meta to have the protocol version and the client capabilities.
mcp () {
    local method="$1" tool="${2:-}" arguments="${3:-}" headers body
    [[ -n "$arguments" ]] || arguments='{}'
    headers=(-H 'content-type: application/json'
             -H 'accept: application/json, text/event-stream'
             -H 'mcp-protocol-version: 2026-07-28'
             -H "mcp-method: ${method}")
    if [[ -n "$tool" ]]; then
        headers+=(-H "mcp-name: ${tool}")
    fi
    body="$(jq -cn --arg method "$method" --arg tool "$tool" --argjson arguments "$arguments" '
        {jsonrpc: "2.0", id: 1, method: $method,
         params: ((if $tool == "" then {} else {name: $tool, arguments: $arguments} end) + {
             _meta: {
                 "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                 "io.modelcontextprotocol/clientInfo": {name: "curl", version: "1.0.0"},
                 "io.modelcontextprotocol/clientCapabilities": {}}})}')"
    shift "$(($# < 3 ? $# : 3))"
    _curl -X POST "http://localhost:${PORT_PROXY}/mcp" "${headers[@]}" -d "$body" "$@"
}

run_log "Discover the server: the bridge answers server/discover itself, at protocol version 2026-07-28"
mcp server/discover | jq -e '
    .result.resultType == "complete"
    and (.result.supportedVersions | index("2026-07-28") != null)
    and .result.capabilities.tools != null
    and (.result._meta["io.modelcontextprotocol/serverInfo"] | has("name") and has("version"))'

run_log "List the tools: the bridge answers tools/list from its configuration"
mcp tools/list | jq -e '
    .result.resultType == "complete"
    and ([.result.tools[].name] == ["get_weather", "create_order", "stream_text"])'

run_log "Call get_weather: the bridge sends GET /v1/weather/Paris?units=imperial to the REST API"
mcp tools/call get_weather '{"city": "Paris", "units": "imperial"}' | jq -e '
    .result.isError == false
    and (.result.content[0].text | fromjson)
        == {city: "Paris", conditions: "sunny", temperature: 72, units: "imperial"}'

run_log "Call create_order: the bridge sends the arguments as the JSON body of POST /v1/orders"
mcp tools/call create_order '{"item": "widget", "quantity": 3}' | jq -e '
    .result.isError == false
    and (.result.content[0].text | fromjson)
        == {id: "order-1", status: "created", order: {item: "widget", quantity: 3}}'

run_log "Call stream_text: a chunked JSON result, with a text item for each of the REST API's server-sent events"
stream="$(mcp tools/call stream_text '{}' -i | tr -d '\r')"
grep -qix 'transfer-encoding: chunked' <<< "$stream"
grep -qix 'content-type: application/json' <<< "$stream"
sed '1,/^$/d' <<< "$stream" | jq -e '
    .result.isError == false
    and ([.result.content[].text] | join(" "))
        == "The REST API sends this answer in three events."'

run_log "Call get_weather for a city that the REST API does not know: its 404 is a tool error"
mcp tools/call get_weather '{"city": "Atlantis"}' | jq -e '
    .result.isError == true
    and (.result.content[0].text | fromjson) == {error: "No weather for Atlantis."}'

run_log "Send a request that is not MCP: the MCP filter rejects it with a 400"
not_mcp=(-X POST "http://localhost:${PORT_PROXY}/mcp" -H 'content-type: application/json' -d '{"city": "Paris"}')
responds_with "request must be a valid JSON-RPC 2.0 message for MCP" "${not_mcp[@]}"
responds_with 400 -o /dev/null -w '%{http_code}' "${not_mcp[@]}"

run_log "Check the access log: what the MCP filter read, and the REST request that the bridge sent"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F 'tools/call get_weather -> GET /v1/weather/Paris?units=imperial 200 via_upstream'"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F 'tools/call create_order -> POST /v1/orders 200 via_upstream'"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F -- '- - -> POST /mcp 400 mcp_not_jsonrpc'"
