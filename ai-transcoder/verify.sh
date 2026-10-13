#!/bin/bash -e

export NAME=ai-transcoder

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

chat () {
    local model="$1" stream="${2:-false}"
    _curl -X POST "http://localhost:${PORT_PROXY}/v1/chat/completions" \
          -H 'content-type: application/json' \
          -d "{\"model\": \"${model}\", \"stream\": ${stream}, \"messages\": [{\"role\": \"user\", \"content\": \"In one short sentence, what is Envoy proxy?\"}]}"
}

run_log "Chat with a Claude model: the Anthropic mock answers, as an OpenAI chat.completion"
chat claude-haiku-4-5 | jq -e '
    .object == "chat.completion"
    and .model == "claude-haiku-4-5"
    and .choices[0].message == {
        content: "Envoy is an open-source, high-performance proxy for cloud-native applications.",
        role: "assistant"}'

run_log "Send the same request to each provider: only the model changes"
for model in gpt-4o-mini claude-haiku-4-5 gemini-2.5-flash; do
    chat "$model" | jq -e --arg model "$model" '
        .object == "chat.completion"
        and .model == $model
        and (.choices[0].message.content | startswith("Envoy is"))'
done

run_log "Stream from a Gemini model: the deltas assemble the reply"
stream="$(chat gemini-2.5-flash true | tr -d '\r')"
sed -n 's/^data: //p' <<< "$stream" \
    | grep -vx '\[DONE\]' \
    | jq -e -s '
        all(.object == "chat.completion.chunk")
        and (map(.choices[0].delta.content) | join("")
             | startswith("Envoy is a high-performance"))'

run_log "Check the stream ends with data: [DONE]"
grep -qx 'data: \[DONE\]' <<< "$stream"

run_log "Check the access log: each request went to its provider's mock"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F 'gpt-4o-mini -> openai /v1/chat/completions 200'"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F 'claude-haiku-4-5 -> anthropic /v1/messages 200'"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F 'gemini-2.5-flash -> gemini /v1beta/models/gemini-2.5-flash:generateContent 200'"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} logs proxy | grep -F 'gemini-2.5-flash -> gemini /v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse 200'"

run_log "Answer a model that no provider serves with a local OpenAI error"
chat llama-3.1-8b | jq -e '.error.code == "model_not_found"'

run_log "Check the transcoder's statistics: everything transcoded, nothing failed"
responds_with \
    "ai_protocol_manager.transcoder.failed: 0" \
    "http://localhost:${PORT_ADMIN}/stats?filter=ai_protocol_manager.transcoder"
responds_with \
    "ai_protocol_manager.transcoder.unresolved: 0" \
    "http://localhost:${PORT_ADMIN}/stats?filter=ai_protocol_manager.transcoder"
responds_without \
    "ai_protocol_manager.transcoder.transcoded: 0" \
    "http://localhost:${PORT_ADMIN}/stats?filter=ai_protocol_manager.transcoder"
