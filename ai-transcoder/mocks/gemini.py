"""Mock of the Gemini API's generateContent methods, with a canned reply."""

import json

from aiohttp import web

routes = web.RouteTableDef()

REPLY = (
    "Envoy is a high-performance, open-source edge and service proxy "
    "for cloud-native applications.")


def generate_content_response(model, text, finish_reason=None):
    candidate = {"content": {"parts": [{"text": text}], "role": "model"}, "index": 0}
    if finish_reason:
        candidate["finishReason"] = finish_reason
    return {
        "candidates": [candidate],
        "usageMetadata": {
            "promptTokenCount": 18,
            "candidatesTokenCount": 17,
            "totalTokenCount": 35},
        "modelVersion": model,
        "responseId": "mock-gemini-000"}


@routes.post("/v1beta/models/{model_and_method}")
async def generate_content(request):
    model, _, method = request.match_info["model_and_method"].partition(":")
    await request.json()
    if method == "generateContent":
        return web.json_response(generate_content_response(model, REPLY, "STOP"))
    if method != "streamGenerateContent" or request.query.get("alt") != "sse":
        raise web.HTTPNotFound()
    response = web.StreamResponse(headers={"content-type": "text/event-stream"})
    await response.prepare(request)
    head, tail = REPLY.split(" for")
    chunks = [
        generate_content_response(model, head),
        generate_content_response(model, f" for{tail}", "STOP")]
    for data in chunks:
        await response.write(f"data: {json.dumps(data)}\n\n".encode())
    await response.write_eof()
    return response


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="0.0.0.0", port=8080)
