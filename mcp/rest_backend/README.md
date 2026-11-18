To learn about this sandbox and for instructions on how to run it please head over
to the [Envoy docs](https://www.envoyproxy.io/docs/envoy/latest/start/sandboxes/mcp.html).

# MCP JSON-REST bridge end-to-end test: MCP 2026-07-28, checked against the specification

The REST backend of the `mcp` sandbox: [`../verify.sh`](../verify.sh) runs it after the MCP
backend's suite, and [`../README.md`](../README.md) has the quick start. These notes are for
developers of the test.

It tests Envoy's MCP JSON-REST bridge (`envoy.filters.http.mcp_json_rest_bridge`) end to end, with
the official MCP Python SDK, pinned to 2.2.0, and raw HTTP, in front of a REST backend:

```text
rest_client.py -> Envoy :10000, listener C: mcp -> mcp_json_rest_bridge -> router -> rest_server.py
               -> Envoy :10001, listener B: mcp_json_rest_bridge -> router -------->
```

- **Listener C** puts the MCP filter (`REJECT_NO_MCP`) in front of the bridge: the chain that this
  suite treats as supported for 2026-07-28. Its tools/list uses `tool_list_http_rule`, transcoded
  to [`rest_server.py`](rest_server.py)'s `GET /v1/tools`, which returns the 2025-11-25
  `ListToolsResult` that the API docs reference.
- **Listener B** is the bridge alone, so the bridge is the MCP server. Its tools/list uses
  `tool_list_local`.

Both listeners have the same four tools ([`envoy.yaml`](envoy.yaml), YAML anchors). The expected
behavior comes from the
[MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28) and the
bridge's API docs, not from what the bridge does today: each check cites a requirement of
[`requirements.py`](requirements.py), with its level (MUST, SHOULD, CONTRACT or SDK) and source.

## What it tests

Each case runs on one listener, or on both, as `name@B` and `name@C`. The 11 cases, in
[`rest_cases.py`](rest_cases.py):

| Case | What it checks |
|---|---|
| `tools-list.local@B` | tools/list, answered by the bridge: the configured tools in order, cache hints, the 2026-07-28 schema, and no REST request |
| `tools-list.http-rule@C` | tools/list, transcoded to `GET /v1/tools`: the backend's tools, and the 2026-07-28 fields that G2 leaves out |
| `sdk.call-tool-direct@C` | The SDK's session sends tools/call of `get_weather`, without the implicit tools/list of `Client.call_tool`, and parses the REST answer: an SDK call through the MCP filter, the bridge and the REST backend |
| `params.valid@B`, `@C` | `get_forecast` with matching `Mcp-Param-*` headers: a result, and the REST backend gets the headers as sent |
| `params.mismatch@C` | `Mcp-Param-City: Lyon` for the argument `Paris`: 400, -32020, and no REST request |
| `transcoding.get@B`, `@C` | `get_weather`: a path variable and a query parameter, `GET /v1/weather/Paris?units=imperial` with no body, and the REST answer as text content |
| `transcoding.body-star@C` | `create_order`: body `"*"`, `POST /v1/orders` with the arguments as JSON, and the 201 answer as text content |
| `transcoding.streaming@C` | `stream_text`: a chunked REST answer, streamed as one text item |
| `errors.empty-body@B` | A POST with an empty body gets 400 and -32700 at once, rather than hanging (envoyproxy/envoy#48635). On listener C, the MCP filter rejects it before the bridge. |

## Regression and compliance checks

- **A regression check** must pass: a failure fails the run (exit 1).
- **A compliance check** names a known gap (`gap="G2"`) of `KNOWN_GAPS` in
  [`requirements.py`](requirements.py), which says what happens and where. It fails on the current
  Envoy, for that reason, and is reported (`GAP`) without failing the run.
- **A known gap's check that passes** is reported as `FIXED`, with a warning, and does not fail the
  run either, because Envoy's `dev` image moves on. Remove the gap from the check, which then
  guards against a regression.

| Gap | What the bridge does on Envoy's current `dev` image | Requirement | Checks |
|---|---|---|---|
| G2 | tools/list from the REST backend is passed through as is: no `resultType`, `ttlMs` or `cacheScope` | MUST | 4 |
| G12 | Results have no `_meta` `serverInfo` (only discover's do) | SHOULD | 3 |

## Run

From this directory, after the setup in [`../README.md`](../README.md#quick-start):

```sh
docker compose up --build -d
docker compose exec rest-client python -u docker/client_entrypoint.py
# Again, for some cases only: each run needs services that have just started.
docker compose up -d --force-recreate
docker compose exec -e ONLY=params.,tools-list.local@B \
  rest-client python -u docker/client_entrypoint.py
docker compose down -v
```

`docker compose exec` returns the client's exit code: it prints `PASS` when no regression check
fails. `ONLY` and `SKIP_CASES` take comma-separated case names, or name prefixes, to run or not to
run. `ENVOY_IMAGE`, `ENVOY_VARIANT`, `LOG_LEVEL` and `RUN_DIR` work as for the MCP backend.

## Reproducing a failure

The client prints one line per check: `ok`, `FAIL` (a regression failure), `GAP G<n>` or `FIXED`,
with what was expected and what came back. For a case with a `FAIL`, it also prints each HTTP
request as sent, and its answer. Then it prints a summary, with the known gaps' failing checks.

The run directory, `/e2e-run`, has the client's output (`client_output.txt`), Envoy's access log
(`access.log`, with the REST method and path after transcoding, and both filters' dynamic
metadata), the REST backend's request log (`rest_requests.jsonl`, with raw paths, headers and
bodies), and `server_info.json`. Every request carries an `X-E2E-Case` header with the case's name,
which the bridge forwards: look a case up in both logs, for example
`docker compose exec rest-client grep '"params.valid@C"' /e2e-run/access.log /e2e-run/rest_requests.jsonl`.
For the filters' debug lines, run `LOG_LEVEL=debug docker compose up -d --force-recreate`, run the
case again, and read `docker compose logs envoy`. To keep the files, before `docker compose down -v`,
run `docker cp "$(docker compose ps -aq rest-client)":/e2e-run/. /tmp/rest-e2e-run`.

## The Envoy image

Envoy is built from `envoyproxy/envoy:dev`, as for the MCP backend. An image of an older commit
(`ENVOY_VARIANT=dev-<commit>`) needs at least envoyproxy/envoy#47331, envoyproxy/envoy#47473,
envoyproxy/envoy#47878, envoyproxy/envoy#48125 and envoyproxy/envoy#48635, for the bridge, and the
MCP filter changes that [`../README.md`](../README.md#quick-start) lists. A newer image must cause
no regression failure: expect `FIXED` lines for the gaps that it fixes.

## Changing the suite

- **A new case.** Add it to `rest_cases.py` with `@case(name, what, listeners)`. Cite a requirement
  of `requirements.py` in each check, adding the requirement first, with its source, if it is new.
  Take expected REST answers from `rest_server.route`, through `rest_answer`. A new tool goes into
  both `envoy.yaml` and `rest_server.TOOLS`, in the same order.
- **A new gap.** When a check fails, first confirm the expectation against its source. Then add the
  gap to `KNOWN_GAPS`, with what happens and where, name it on the failing checks only, and leave
  the expectation as it is.
- **A fixed gap.** Remove `gap=` from the checks that report `FIXED`, and the gap from `KNOWN_GAPS`
  when no check names it.

## Files

| File | What |
|---|---|
| [`envoy.yaml`](envoy.yaml), [`rest_server.py`](rest_server.py) | Envoy's config, with listeners C and B, and the REST backend, with its request log |
| [`requirements.py`](requirements.py), [`rest_cases.py`](rest_cases.py) | The requirements and known gaps, and the cases |
| [`rest_client.py`](rest_client.py) | The runner: raw HTTP, SDK sessions, the checks and their summary |
| [`docker-compose.yaml`](docker-compose.yaml), [`docker/`](docker) | The services, the server's entrypoint, and the client's test run |
