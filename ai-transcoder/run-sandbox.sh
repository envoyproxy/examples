#!/bin/bash -e
#
# Starts the sandbox, then follows Envoy's log. In a terminal, it first asks for each API key, without
# echoing it, and for the Vertex AI project; Enter keeps the value this shell already has.
#
# Optional environment variables:
#   PORT_PROXY, PORT_ADMIN  Host ports for Envoy's listener and admin interface (10000 and 9901).
#   VERTEX_LOCATION         Vertex AI location (global).
#   ENVOY_VARIANT           The envoyproxy/envoy image tag to build on (dev).
#   COMPOSE_BUILD           The command that builds the image (docker compose build), for example one
#                           that runs Docker Compose where BuildKit is available.

set -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

export PORT_PROXY="${PORT_PROXY:-10000}" PORT_ADMIN="${PORT_ADMIN:-9901}"
export VERTEX_LOCATION="${VERTEX_LOCATION:-global}"
ENVOY_VARIANT="${ENVOY_VARIANT:-dev}"
read -ra build <<< "${COMPOSE_BUILD:-docker compose build}"

log () {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

# Shows enough of a key to tell which one it is.
masked () {
    printf '%s...%s, %d characters' "${1:0:10}" "${1: -4}" "${#1}"
}

# Asks for a variable. Enter keeps the value from this shell, or leaves it unset.
ask () {
    local name="$1" secret="$2" value hint="Enter to skip"
    if [[ -n "${!name}" ]]; then
        hint="Enter to keep the one from your shell"
    fi
    if [[ "$secret" == secret ]]; then
        read -r -s -p "${name} (${hint}): " value
        echo
    else
        read -r -p "${name} (${hint}): " value
    fi
    if [[ -n "$value" ]]; then
        printf -v "$name" '%s' "$value"
    fi
    export "${name?}"
}

if [[ -t 0 ]]; then
    ask OPENAI_API_KEY secret
    ask ANTHROPIC_API_KEY secret
    ask VERTEX_API_KEY secret
    if [[ -n "$VERTEX_API_KEY" ]]; then
        ask VERTEX_PROJECT
    fi
fi

log "Providers:"
for name in OPENAI_API_KEY ANTHROPIC_API_KEY VERTEX_API_KEY; do
    if [[ -n "${!name}" ]]; then
        log "  ${name}: $(masked "${!name}")"
    else
        log "  ${name}: not set, so that provider answers with its own authentication error"
    fi
done
if [[ -n "$VERTEX_PROJECT" ]]; then
    log "  Vertex AI: project ${VERTEX_PROJECT}, location ${VERTEX_LOCATION}"
else
    log "  Vertex AI: VERTEX_PROJECT is not set, so requests for Gemini models will fail"
fi

log "Building the proxy on envoyproxy/envoy:${ENVOY_VARIANT}, with: ${build[*]}"
if ! "${build[@]}" --build-arg "ENVOY_VARIANT=${ENVOY_VARIANT}"; then
    log "The build failed. The shared Envoy Dockerfile needs BuildKit (docker buildx); set COMPOSE_BUILD" \
        "to build where it is available."
    exit 1
fi

log "Starting the proxy on localhost:${PORT_PROXY}, with its admin interface on localhost:${PORT_ADMIN}"
docker compose up -d --wait
log "Envoy $(docker compose exec -T proxy envoy --version | grep -o 'version: .*')"
log "Vertex AI requests go to aiplatform.googleapis.com$(docker compose exec -T proxy \
    grep -o '/v1/projects/[^/]*/locations/[^/]*/publishers/google/models/' /tmp/envoy.yaml)..."

log "Try it from another terminal, for example:"
for model in gpt-4o-mini claude-haiku-4-5 gemini-2.5-flash; do
    printf "  curl -s localhost:%s/v1/chat/completions -H 'content-type: application/json' -d '%s' | jq\n" \
        "$PORT_PROXY" "{\"model\": \"${model}\", \"messages\": [{\"role\": \"user\", \"content\": \"Hi\"}]}"
done
log "Statistics: curl -s 'localhost:${PORT_ADMIN}/stats?filter=ai_protocol_manager'"

log "Following Envoy's log, with each request's model, upstream and response code."
log "Ctrl-C stops following; 'docker compose down' stops the sandbox."
docker compose logs -f --no-log-prefix proxy | grep -v --line-buffered 'work-in-progress'
