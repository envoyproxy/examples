#!/bin/bash -e

export NAME=mcp
export PATHS=.,rest_backend

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

REST_COMPOSE=("${DOCKER_COMPOSE[@]}" -f rest_backend/docker-compose.yaml)

# Whether the REST client failed only because known gaps' checks now pass (FIXED): its results have
# no regression failure (nor, with COMPLIANCE=strict, a known gap's failing check), and Envoy and the
# REST server were still running at the end.
only_known_gaps_fixed () {
    local results output
    results="$("${REST_COMPOSE[@]}" exec -T rest-client cat /e2e-run/results.json)" || return 1
    output="$("${REST_COMPOSE[@]}" exec -T rest-client cat /e2e-run/client_output.txt)" || return 1
    jq -e --arg compliance "${COMPLIANCE:-}" \
        '.summary | .failed == 0 and .known_gap_passes > 0
            and ($compliance != "strict" or .known_gap_failures == 0)' \
        <<< "$results" > /dev/null \
        && [[ "$(grep -c ' is still running$' <<< "$output")" -eq 2 ]]
}


run_log "MCP backend: run the regression cases"
"${DOCKER_COMPOSE[@]}" exec -T mcp-client python -u docker/client_entrypoint.py

run_log "MCP backend: restart with the demo tools, and run the developer demo"
# Recreate the three services, in order, as when they were started: the server clears the run
# directory, so Envoy has to start after it, and open a new access log.
DEMO=1 "${DOCKER_COMPOSE[@]}" up --wait -d --force-recreate
"${DOCKER_COMPOSE[@]}" exec -T mcp-client python -u docker/client_entrypoint.py

run_log "REST backend: run the MCP JSON-REST bridge cases"
status=0
"${REST_COMPOSE[@]}" exec -T rest-client python -u docker/client_entrypoint.py || status=$?
if [[ "$status" -ne 0 ]]; then
    # The client also fails when a known gap's check now passes (FIXED), so that the gap gets
    # removed from its checks. Envoy's dev image moves on, so that is reported here, not failed.
    only_known_gaps_fixed || exit "$status"
    run_log "WARNING: known gaps' checks now pass (FIXED, above): remove the gaps from those checks (rest_backend/README.md)"
fi

run_log "REST backend: check the report and the results in the run directory"
"${REST_COMPOSE[@]}" exec -T rest-client ls -l /e2e-run/report.txt /e2e-run/results.json
