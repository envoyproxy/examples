"""Mock OpenAI Chat Completions API, returning canned, deterministic responses."""

import json

from aiohttp import web

CONTENT = (
    "Envoy is an open-source edge and service proxy"
    " designed for cloud-native applications.")
CREATED = 1735689600
COMPLETION_ID = "chatcmpl-00000sandbox"

routes = web.RouteTableDef()


@routes.post("/v1/chat/completions")
async def chat_completions(request):
    body = await request.json()
    model = body["model"]
    if body.get("stream"):
        return await stream_completion(request, model)
    return web.json_response({
        "id": COMPLETION_ID,
        "object": "chat.completion",
        "created": CREATED,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": CONTENT},
            "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 18,
            "completion_tokens": 13,
            "total_tokens": 31}})


async def stream_completion(request, model):
    response = web.StreamResponse()
    response.content_type = "text/event-stream"
    await response.prepare(request)
    head, tail = CONTENT[:46], CONTENT[46:]
    chunks = [
        {"delta": {"role": "assistant", "content": head}, "finish_reason": None},
        {"delta": {"content": tail}, "finish_reason": "stop"}]
    for chunk in chunks:
        event = {
            "id": COMPLETION_ID,
            "object": "chat.completion.chunk",
            "created": CREATED,
            "model": model,
            "choices": [dict(index=0, **chunk)]}
        await response.write(f"data: {json.dumps(event)}\n\n".encode())
    await response.write(b"data: [DONE]\n\n")
    await response.write_eof()
    return response


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="0.0.0.0", port=8080)
