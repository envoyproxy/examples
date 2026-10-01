#!/bin/bash -e

export NAME=ai-transcoder
export PORT_PROXY="${AI_TRANSCODER_PORT_PROXY:-12900}"
export PORT_ADMIN="${AI_TRANSCODER_PORT_ADMIN:-12901}"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

chat () {
    local model="$1" stream="${2:-false}"
    _curl -X POST "http://localhost:${PORT_PROXY}/v1/chat/completions" \
          -H 'content-type: application/json' \
          -d "{\"model\": \"${model}\", \"stream\": ${stream}, \"messages\": [{\"role\": \"user\", \"content\": \"In one short sentence, what is Envoy proxy?\"}]}"
}

# A provider is only sent requests when the variables it needs, such as its API key, are set.
test_provider () {
    local required="$1" model="$2" unary_upstream="$3" stream_upstream="$4" stream var
    for var in $required; do
        if [[ -z "${!var}" ]]; then
            run_log "Skip ${model}: set ${var} to send it to its provider"
            return
        fi
    done

    run_log "Chat with ${model}: the reply is an OpenAI chat.completion"
    chat "$model" | jq -e '.object == "chat.completion" and (.choices[0].message.content | length > 0)'

    run_log "Stream from ${model}: OpenAI chat.completion.chunk events, then data: [DONE]"
    stream="$(chat "$model" true | tr -d '\r')"
    grep -qx 'data: \[DONE\]' <<< "$stream"
    sed -n 's/^data: //p' <<< "$stream" \
        | grep -vx '\[DONE\]' \
        | jq -e -s 'length > 0 and all(.object == "chat.completion.chunk")'

    run_log "Check the access log: ${model} went to ${unary_upstream}, and to ${stream_upstream} when streaming"
    wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F '${model} -> ${unary_upstream} 200'"
    wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F '${model} -> ${stream_upstream} 200'"
}

run_log "Answer a model that no route serves with a local OpenAI error"
chat llama-3.1-8b | jq -e '.error.code == "model_not_found"'

test_provider OPENAI_API_KEY gpt-4o-mini \
    api.openai.com/v1/chat/completions \
    api.openai.com/v1/chat/completions
test_provider ANTHROPIC_API_KEY claude-haiku-4-5 \
    api.anthropic.com/v1/messages \
    api.anthropic.com/v1/messages
VERTEX_MODEL_PATH="aiplatform.googleapis.com/v1/projects/${VERTEX_PROJECT}/locations/${VERTEX_LOCATION:-global}/publishers/google/models/gemini-2.5-flash"
test_provider "VERTEX_API_KEY VERTEX_PROJECT" gemini-2.5-flash \
    "${VERTEX_MODEL_PATH}:generateContent" \
    "${VERTEX_MODEL_PATH}:streamGenerateContent?alt=sse"

run_log "Check that no request or response failed to transcode"
responds_with \
    "ai_protocol_manager.transcoder.failed: 0" \
    "http://localhost:${PORT_ADMIN}/stats?filter=transcoder"
