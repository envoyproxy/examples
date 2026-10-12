#!/bin/bash -e

export NAME=ai-transcoder
export PORT_PROXY="${AI_TRANSCODER_PORT_PROXY:-12900}"
export PORT_ADMIN="${AI_TRANSCODER_PORT_ADMIN:-12901}"

ANSWER="Envoy is an open-source edge and service proxy designed for cloud-native applications."

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

chat () {
    local model="$1" stream="${2:-false}"
    _curl -X POST "http://localhost:${PORT_PROXY}/v1/chat/completions" \
          -H 'content-type: application/json' \
          -d "{\"model\": \"${model}\", \"stream\": ${stream}, \"messages\": [{\"role\": \"user\", \"content\": \"In one short sentence, what is Envoy proxy?\"}]}"
}

run_log "Chat with claude-haiku-4-5: the reply is an OpenAI chat.completion"
chat claude-haiku-4-5 \
    | jq -e --arg answer "$ANSWER" '
        .object == "chat.completion"
        and .id == "msg_00000sandbox"
        and .choices[0].message.content == $answer'

run_log "Send the same request to each provider"
for model in gpt-4o-mini claude-haiku-4-5 gemini-2.5-flash; do
    chat "$model" \
        | jq -e --arg model "$model" --arg answer "$ANSWER" '
            .object == "chat.completion"
            and .model == $model
            and .choices[0].message.content == $answer'
done

for model in gpt-4o-mini claude-haiku-4-5 gemini-2.5-flash; do
    run_log "Stream from ${model}: OpenAI chat.completion.chunk events, then data: [DONE]"
    stream="$(chat "$model" true | tr -d '\r')"
    grep -qx 'data: \[DONE\]' <<< "$stream"
    sed -n 's/^data: //p' <<< "$stream" \
        | grep -vx '\[DONE\]' \
        | jq -e -s --arg model "$model" --arg answer "$ANSWER" '
            length > 0
            and all(.object == "chat.completion.chunk" and .model == $model)
            and (map(.choices[0].delta.content // "") | join("")) == $answer'
done

run_log "Answer a model that no route serves with a local OpenAI error"
chat llama-3.1-8b | jq -e '.error.code == "model_not_found"'
[[ "$(_curl -o /dev/null -w '%{http_code}' -X POST "http://localhost:${PORT_PROXY}/v1/chat/completions" \
       -H 'content-type: application/json' \
       -d '{"model": "llama-3.1-8b", "messages": [{"role": "user", "content": "Hi"}]}')" == "404" ]]

run_log "Check the access log: each request went to its provider's cluster and path"
for entry in \
    "gpt-4o-mini -> openai/v1/chat/completions 200" \
    "claude-haiku-4-5 -> anthropic/v1/messages 200" \
    "gemini-2.5-flash -> gemini/v1beta/models/gemini-2.5-flash:generateContent 200" \
    "gemini-2.5-flash -> gemini/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse 200" \
    "llama-3.1-8b -> -/v1/chat/completions 404"; do
    wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F '${entry}'"
done

run_log "Check that payloads transcoded, and none failed"
responds_with \
    "ai_protocol_manager.transcoder.failed: 0" \
    "http://localhost:${PORT_ADMIN}/stats?filter=ai_protocol_manager.transcoder"
transcoded="$(_curl "http://localhost:${PORT_ADMIN}/stats?filter=ai_protocol_manager.transcoder" \
    | grep -oP 'transcoder\.transcoded: \K\d+')"
(( transcoded > 0 ))
