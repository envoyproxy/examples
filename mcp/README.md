To learn about this sandbox and for instructions on how to run it please head over
to the [Envoy docs](https://www.envoyproxy.io/docs/envoy/latest/start/sandboxes/mcp.html).

# MCP sandbox: end-to-end tests of the MCP filter and the MCP JSON-REST bridge

Two Docker Compose projects test Envoy at MCP protocol version 2026-07-28, with the official MCP
Python SDK, the [`mcp`](https://pypi.org/project/mcp/) package pinned to 2.2.0, and raw HTTP:
- this directory: the MCP filter (`envoy.filters.http.mcp`) in front of an MCP server, with 17
  regression cases;
- [`rest_backend/`](rest_backend): the MCP JSON-REST bridge in front of a REST backend, with 11
  cases checked against the MCP specification (see its [README](rest_backend/README.md)).

These notes are for developers of the tests. [`example.rst`](example.rst) is the sandbox's page in
Envoy's docs.

## Quick start

You need Docker, or rootless Podman, with Docker Compose v2. With rootless Podman, first run:

```sh
systemctl --user start podman.socket
export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/podman/podman.sock"
export DOCKER_BUILDKIT=0  # Podman's API has no BuildKit: Compose builds with its classic builder
```

[`verify.sh`](verify.sh) starts both projects, runs both suites, and stops the projects, as the
examples' CI does. It exits 0 when both suites pass:

```sh
./verify.sh
```

To run this suite by hand, from this directory:

```sh
docker compose up --build -d
docker compose exec mcp-client python -u docker/client_entrypoint.py  # exit 0 for PASS, 1 for FAIL
docker compose down -v
```

The client service only waits (`sleep infinity`), and the cases run in it, with
`docker compose exec`. Each run needs services that have just started, because the server clears
the shared run directory when it starts: to run the cases again, first run
`docker compose up -d --force-recreate`.

| Variable | Default | |
|---|---|---|
| `ENVOY_IMAGE`, `ENVOY_VARIANT` | `envoyproxy/envoy`, `dev` | The image that Envoy's image is built from, `${ENVOY_IMAGE}:${ENVOY_VARIANT}` in `../shared/envoy/Dockerfile`: for example `ENVOY_VARIANT=dev-<commit>` for a pinned build |
| `SKIP_CASES` | unset | Comma-separated names of cases not to run. Each is reported as `SKIP` |
| `LOG_LEVEL` | `info` | Envoy's log level |
| `RUN_DIR` | the `run` volume | A host directory for the run directory |

`docker compose up` applies them when it creates the containers. `SKIP_CASES` also works with
`docker compose exec -e`. To test a local Envoy build, put the binary into an image of its own:

```sh
cp /path/to/envoy-static /tmp/envoy-local/envoy
printf 'FROM envoyproxy/envoy:dev\nCOPY envoy /usr/local/bin/envoy\n' > /tmp/envoy-local/Dockerfile
docker build -t envoy-local:dev /tmp/envoy-local
ENVOY_IMAGE=envoy-local ENVOY_VARIANT=dev docker compose up --build -d
```

Use a build that includes the Envoy features exercised by the test suite you are running. As the
Ubuntu-based variants do, the image also needs `apt-get` and its own `/docker-entrypoint.sh`.

## What the cases check

```
mcp_client.py ──▶ Envoy: envoy.filters.http.mcp ─▶ router ──▶ mcp_server.py
                  envoy:10000, the main listener              mcp-server:8000/mcp
                  envoy:10001, capped at 2025-11-25
```

The MCP backend suite exercises the filter with `attribute_source: BODY` and
`traffic_mode: REJECT_NO_MCP`, on both listeners.

The server has one tool, `get_weather(city)`, whose result is fixed. For each case, the client
checks the response, Envoy's access log entry with the MCP filter's dynamic metadata, the MCP
filter's counters (`http.ingress_http.mcp.*`), and the server's request log, which shows whether
the request reached the server. Each check prints `ok` or `FAIL`, and any `FAIL` fails the run.

The SDK cases use `Client(url, mode="2026-07-28")`, which sends no `initialize` handshake and no
`server/discover` probe, with no response cache:

| Case | Request | Expected |
|---|---|---|
| `sdk-stateless-tools` | `tools/list`, then `tools/call` of `get_weather` with `{"city": "Paris"}`, through the main listener | `get_weather`, and `Paris: sunny, 22C`. Envoy logged these two `POST`s and no other request, each with the 2026-07-28 headers and no `Mcp-Session-Id`, forwarded to the server, which answered 200. The MCP filter's metadata has `status: mcp_ok` and exactly the SDK's `params._meta`, with client capabilities `{}`. The server created no session, and no counter changed. |
| `sdk-unsupported-version` | `tools/list` through the capped listener | `MCPError` -32022 `Unsupported MCP protocol version: 2026-07-28`, with the supported versions as data. Envoy answered 400 itself, and logged no other request, so the client did not fall back to the handshake. The server received nothing. |

The raw HTTP cases go through the main listener. Each sends what the SDK sends, but for the one
thing in the Request column, and an `X-E2E-Case` header with its name, by which the client finds it
in both logs:

| Case | Request | Expected response | Counter |
|---|---|---|---|
| `base64-mcp-name` | `tools/call` with `Mcp-Name: =?base64?Z2V0X3dlYXRoZXI=?=` | 200 from the server, with the tool result | |
| `missing-mcp-method` | `tools/list` without `Mcp-Method` | 400, -32020 `Missing required Mcp-Method header`, `id: null` | `header_mismatch` +1 |
| `missing-mcp-name` | `tools/call` without `Mcp-Name` | 400, -32020 `Missing required Mcp-Name header`, `id: null` | `header_mismatch` +1 |
| `invalid-base64-mcp-name` | `tools/call` with `Mcp-Name: =?base64?%%%?=` | 400, -32020 `Invalid Base64-encoded Mcp-Name header`, `id: null` | `header_mismatch` +1 |
| `mcp-method-mismatch` | `Mcp-Method: tools/list` on a `tools/call` body | 400, -32020 `MCP header attributes do not match request body`, the request's `id` | `header_mismatch` +1 |
| `mcp-name-mismatch` | `Mcp-Name: get_weather` on a `tools/call` of `get_forecast` | 400, -32020 `MCP header attributes do not match request body`, the request's `id` | `header_mismatch` +1 |
| `protocol-version-mismatch` | `params._meta` protocol version 2025-11-25 | 400, -32020 `MCP-Protocol-Version header does not match request body`, the request's `id` | `header_mismatch` +1 |
| `unknown-protocol-version` | `MCP-Protocol-Version: 2099-01-01` | 400, -32022 `Unsupported MCP protocol version: 2099-01-01`, `id: null`, with the five versions the filter knows as `supported` | |
| `missing-client-capabilities` | `params._meta` without `io.modelcontextprotocol/clientCapabilities` | 400, -32602 `Missing required params._meta field: io.modelcontextprotocol/clientCapabilities`, the request's `id` | |
| `missing-meta` | `tools/list` with no `params`, so no `params._meta` | 400, -32602 `Missing or invalid params._meta field: io.modelcontextprotocol/protocolVersion`, the request's `id` | |
| `missing-client-capabilities-id-last` | As `missing-client-capabilities`, but with the `id` after `params` | 400, -32602 `Missing required params._meta field: io.modelcontextprotocol/clientCapabilities`, the request's `id` | |
| `session-delete` | `DELETE` with an `Mcp-Session-Id` | 405, text `MCP DELETE is not supported for protocol version 2026-07-28`, `Allow: POST` | |
| `sse-get` | `GET` with `Accept: text/event-stream` | 405, text `MCP GET with SSE is not supported for protocol version 2026-07-28`, `Allow: POST` | |
| `legacy-initialize` | `initialize`, the legacy handshake | 404 from the server, -32601 `Method not found`, `data: "initialize"`, the request's `id` | |
| `legacy-initialized-notification` | `notifications/initialized`, a notification, with no `id` | 202 from the server, with no body | |

For the three cases that reach the server, Envoy passed on the server's status
(`response_code_details: via_upstream`), the MCP filter's metadata has `status: mcp_ok` and the
attributes that it parsed, and the server logged the request once. For the others, Envoy answered
itself, with no upstream host, the metadata has `status: mcp_not_jsonrpc` (the 405s have none), and
the server received nothing. The other counters (`requests_rejected`, `invalid_json`,
`body_too_large`, `duplicate_keys_rejected`) must not change.

| Envoy change that the cases test | Cases |
|---|---|
| Protocol version enforcement, envoyproxy/envoy#47280: -32022 for a version newer than `max_supported_protocol_version`, or unknown; at 2026-07-28, -32020 for a missing, invalid or mismatched `Mcp-Method` or `Mcp-Name`, or a mismatched protocol version in `params._meta`, a base64-encoded `Mcp-Name`, and 405 for the GET stream and `DELETE` | `sdk-unsupported-version`, `unknown-protocol-version`, `protocol-version-mismatch`, `missing-mcp-method`, `missing-mcp-name`, `invalid-base64-mcp-name`, `mcp-method-mismatch`, `mcp-name-mismatch`, `base64-mcp-name`, `session-delete`, `sse-get` |
| Required client capabilities, envoyproxy/envoy#47915: -32602 for a request, but not a notification, without the key | `missing-client-capabilities`, `missing-client-capabilities-id-last`, `sdk-stateless-tools` |
| Required protocol version in `params._meta`, envoyproxy/envoy#48720: -32602, before the client capabilities check | `missing-meta` |
| Parser path tracking, envoyproxy/envoy#47862: the filter finds an `id` after `params` | `missing-client-capabilities-id-last` |
| None: the filter forwards the legacy handshake at 2026-07-28, as any request whose headers match its body | `legacy-initialize`, `legacy-initialized-notification` |

### Expectations that depend on the pinned SDK

The suite is pinned to `mcp` 2.2.0: the image installs that version, and
`docker/client_entrypoint.py` stops for any other. The 404 and the 202 that the `legacy-*` cases
expect are `mcp` 2.2.0's answers, not protocol requirements: 2026-07-28 removes the handshake, but
lets a server answer it in other ways, and `mcp` 2.0.0 refuses the notification with 400 and
-32600. The SDK cases also rely on 2.2.0's client API and on exactly the requests that it sends.

To move to another SDK version, change `MCP_SDK_VERSION` in both `docker/client_entrypoint.py`
files, `docker/requirements.in` (then regenerate `docker/requirements.txt` with the command in its
header), the Python image's tag in both `docker-compose.yaml` files, and the Dependabot `ignore`
entries. Then check what that version sends and answers, and update the expectations.

## Reproducing a failure

The services share a run directory, `/e2e-run`: the `run` volume, or the `RUN_DIR` host directory.

| File | |
|---|---|
| `client_output.txt` | The client's output |
| `access.log` | Envoy's access log: one JSON object per request, with the MCP filter's metadata |
| `backend_requests.jsonl` | The server's request log, with each request's MCP headers and `X-E2E-Case` |
| `stats.txt` | Envoy's stats, read after the last case |
| `server_info.json` | Envoy's version, command line and extensions |

- **A check failed:** its `FAIL` line says what was expected and what came back, and a raw case also
  prints its access log entry. Look the case up in both logs, for example
  `docker compose exec mcp-client grep '"missing-mcp-name"' /e2e-run/access.log /e2e-run/backend_requests.jsonl`.
  A request that the server answered has an upstream host and `via_upstream` in `access.log`.
- **Why the filter did something:** run `LOG_LEVEL=debug docker compose up -d --force-recreate`, run
  the cases again, and look for the `[mcp]` lines in `docker compose logs envoy`.
- **Envoy or the server did not start:** `docker compose logs envoy`, or `mcp-server`, says why. To
  check the config alone, once `docker compose up` has prepared the run directory, run
  `docker compose run --rm --no-deps envoy envoy --mode validate -c /etc/envoy.yaml`.
- **Keep the files:** before `docker compose down -v`, run
  `docker cp "$(docker compose ps -aq mcp-client)":/e2e-run/. /tmp/mcp-e2e-run`, or set `RUN_DIR`.
- **Your own request:** send it to Envoy from the `envoy` container, which has `curl`:

```sh
docker compose exec envoy curl -sS http://localhost:10000/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/call' -H 'mcp-name: get_weather' \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "get_weather", "arguments": {"city": "Paris"}, "_meta": {
          "io.modelcontextprotocol/protocolVersion": "2026-07-28",
          "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
          "io.modelcontextprotocol/clientCapabilities": {}}}}'
```

Envoy runs as its image's non-root `envoy` user: `docker/server_entrypoint.sh` makes the run
directory writable for it.

## Files

| File | |
|---|---|
| [`verify.sh`](verify.sh) | Runs both suites, as the examples' CI does |
| [`docker-compose.yaml`](docker-compose.yaml) | The services: `mcp-client`, `envoy` and `mcp-server` |
| [`envoy.yaml`](envoy.yaml) | Envoy's config: two listeners that differ only in the MCP filter's `max_supported_protocol_version` |
| [`mcp_client.py`](mcp_client.py) | The cases and their checks |
| [`mcp_server.py`](mcp_server.py) | The MCP server: `get_weather(city)` over Streamable HTTP, with a request log |
| [`docker/`](docker) | The Python image (`mcp==2.2.0`, every dependency pinned by hash), the server's entrypoint, and the client's test run |
| [`rest_backend/`](rest_backend) | The MCP JSON-REST bridge's suite |
