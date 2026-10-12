"""Mock Gemini API, returning canned, deterministic responses."""

import json

from aiohttp import web

CONTENT = (
    "Envoy is an open-source edge and service proxy"
    " designed for cloud-native applications.")
RESPONSE_ID = "00000sandbox"

routes = web.RouteTableDef()


def chunk(model, text, finished):
    candidate = {"content": {"parts": [{"text": text}], "role": "model"}, "index": 0}
    usage = {"promptTokenCount": 18, "totalTokenCount": 18}
    if finished:
        candidate["finishReason"] = "STOP"
        usage.update({"candidatesTokenCount": 13, "totalTokenCount": 31})
    return {
        "candidates": [candidate],
        "usageMetadata": usage,
        "modelVersion": model,
        "responseId": RESPONSE_ID}


# The Gemini API carries the model, and whether to stream, in the request path:
# /v1beta/models/{model}:generateContent or {model}:streamGenerateContent?alt=sse
@routes.post("/v1beta/models/{model_and_action}")
async def generate_content(request):
    model, action = request.match_info["model_and_action"].split(":")
    if action == "streamGenerateContent":
        return await stream_content(request, model)
    return web.json_response(chunk(model, CONTENT, finished=True))


async def stream_content(request, model):
    response = web.StreamResponse()
    response.content_type = "text/event-stream"
    await response.prepare(request)
    head, tail = CONTENT[:46], CONTENT[46:]
    for text, finished in [(head, False), (tail, True)]:
        data = json.dumps(chunk(model, text, finished))
        await response.write(f"data: {data}\n\n".encode())
    await response.write_eof()
    return response


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="0.0.0.0", port=8080)
