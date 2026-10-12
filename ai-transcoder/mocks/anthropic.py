"""Mock of the Anthropic Messages API, with a canned reply."""

import json

from aiohttp import web

routes = web.RouteTableDef()

REPLY = (
    "Envoy is an open-source, high-performance proxy "
    "for cloud-native applications.")


def message(model):
    return {
        "id": "msg_mock_000",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": REPLY}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 18, "output_tokens": 14}}


def events(model):
    head, tail = REPLY.split(" for")
    return [
        ("message_start",
         {"type": "message_start",
          "message": {
              "id": "msg_mock_000",
              "type": "message",
              "role": "assistant",
              "model": model,
              "content": [],
              "stop_reason": None,
              "stop_sequence": None,
              "usage": {"input_tokens": 18, "output_tokens": 1}}}),
        ("content_block_start",
         {"type": "content_block_start",
          "index": 0,
          "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta",
         {"type": "content_block_delta",
          "index": 0,
          "delta": {"type": "text_delta", "text": head}}),
        ("content_block_delta",
         {"type": "content_block_delta",
          "index": 0,
          "delta": {"type": "text_delta", "text": f" for{tail}"}}),
        ("content_block_stop",
         {"type": "content_block_stop", "index": 0}),
        ("message_delta",
         {"type": "message_delta",
          "delta": {"stop_reason": "end_turn", "stop_sequence": None},
          "usage": {"output_tokens": 14}}),
        ("message_stop",
         {"type": "message_stop"})]


@routes.post("/v1/messages")
async def messages(request):
    body = await request.json()
    model = body.get("model", "claude-mock")
    if not body.get("stream"):
        return web.json_response(message(model))
    response = web.StreamResponse(headers={"content-type": "text/event-stream"})
    await response.prepare(request)
    for event, data in events(model):
        await response.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
    await response.write_eof()
    return response


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="0.0.0.0", port=8080)
