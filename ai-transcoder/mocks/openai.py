"""Mock of the OpenAI Chat Completions API, with a canned reply."""

import json

from aiohttp import web

routes = web.RouteTableDef()

REPLY = (
    "Envoy is an open-source edge and service proxy "
    "designed for cloud-native applications.")

USAGE = {"prompt_tokens": 18, "completion_tokens": 16, "total_tokens": 34}


def completion(model):
    return {
        "id": "chatcmpl-mock-000",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {"index": 0,
             "message": {"role": "assistant", "content": REPLY},
             "finish_reason": "stop"}],
        "usage": USAGE}


def chunk(model, delta, finish_reason=None):
    return {
        "id": "chatcmpl-mock-000",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": model,
        "choices": [
            {"index": 0,
             "delta": delta,
             "finish_reason": finish_reason}],
        "usage": USAGE}


@routes.post("/v1/chat/completions")
async def chat_completions(request):
    body = await request.json()
    model = body.get("model", "gpt-mock")
    if not body.get("stream"):
        return web.json_response(completion(model))
    response = web.StreamResponse(headers={"content-type": "text/event-stream"})
    await response.prepare(request)
    head, tail = REPLY.split(" designed")
    chunks = [
        chunk(model, {"role": "assistant", "content": head}),
        chunk(model, {"content": f" designed{tail}"}, "stop")]
    for data in chunks:
        await response.write(f"data: {json.dumps(data)}\n\n".encode())
    await response.write(b"data: [DONE]\n\n")
    await response.write_eof()
    return response


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="0.0.0.0", port=8080)
