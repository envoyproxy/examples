"""Mock of a REST API, which Envoy's MCP JSON-REST bridge serves as MCP tools."""

from aiohttp import web

routes = web.RouteTableDef()

WEATHER = {
    "London": {"conditions": "rainy", "temperature": 14},
    "Paris": {"conditions": "sunny", "temperature": 22},
}

STREAM = ("The REST API sends", "this answer", "in three events.")


@routes.get("/v1/weather/{city}")
async def get_weather(request):
    city = request.match_info["city"]
    if city not in WEATHER:
        return web.json_response({"error": f"No weather for {city}."}, status=404)
    units = request.query.get("units", "metric")
    weather = dict(WEATHER[city])
    if units == "imperial":
        weather["temperature"] = round(weather["temperature"] * 9 / 5 + 32)
    return web.json_response({"city": city, **weather, "units": units})


@routes.post("/v1/orders")
async def create_order(request):
    order = await request.json()
    return web.json_response({"id": "order-1", "status": "created", "order": order}, status=201)


@routes.get("/v1/stream/text")
async def stream_text(request):
    response = web.StreamResponse(headers={"content-type": "text/event-stream"})
    await response.prepare(request)
    for text in STREAM:
        await response.write(f"data: {text}\n\n".encode())
    await response.write_eof()
    return response


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    web.run_app(app, host="0.0.0.0", port=8080)
