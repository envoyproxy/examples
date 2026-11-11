To learn about this sandbox and for instructions on how to run it please head over
to the [Envoy docs](https://www.envoyproxy.io/docs/envoy/latest/start/sandboxes/mcp.html).

# MCP JSON-REST bridge end-to-end test: MCP 2026-07-28, checked against the specification

The REST backend of the `mcp` sandbox: [`../verify.sh`](../verify.sh) runs this test after the MCP
backend's. These notes are for developers of the test.

Tests Envoy's MCP JSON-REST bridge (`envoy.filters.http.mcp_json_rest_bridge`) end to end. The
clients are the official MCP Python SDK, pinned to 2.2.0, and raw HTTP. Behind the bridge is a REST
backend:

```text
rest_client.py -> Envoy :10000, listener C: mcp -> mcp_json_rest_bridge -> router -> rest_server.py
               -> Envoy :10001, listener B: mcp_json_rest_bridge -> router -------->
```

The expected behavior comes from the
[MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28) and the
bridge's API docs (`mcp_json_rest_bridge.proto`), not from what the bridge does today.
[`requirements.py`](requirements.py) lists:
- every requirement that a check cites, with its level (MUST, SHOULD, CONTRACT or SDK) and source;
- the implementation gaps that the suite knows of.

A check of a requirement that Envoy does not meet yet stays in the suite, at full strength. It
becomes a compliance check that names its gap, and every run reports it.

This directory shares the MCP backend's Python image ([`../docker`](../docker)), and does not change
it. See [`../README.md`](../README.md) for the MCP backend's test.

## What it tests

**Listeners.**
- **C** puts the MCP filter (`REJECT_NO_MCP`) in front of the bridge: the chain that this suite
  treats as supported for 2026-07-28. The MCP filter checks the MCP headers, the protocol version
  and the client capabilities first.
- **B** is the bridge alone, so the bridge is the MCP server.

The two listeners have the same tools ([`envoy.yaml`](envoy.yaml), YAML anchors). Each case runs on
one listener, or on both, as `name@B` and `name@C`.

**tools/list in both of the bridge's modes.**
- B uses `tool_list_local`.
- C uses `tool_list_http_rule`, transcoded to [`rest_server.py`](rest_server.py)'s `GET /v1/tools`.
  That endpoint returns the 2025-11-25 `ListToolsResult` that the API docs reference: it has no
  2026-07-28 fields that would hide a gap.

**Tools.** Sixteen tools cover the transcoder:
- path variables, `{var=pattern}`, nested and repeated query parameters;
- body `"*"` and a named body field;
- GET, POST, PUT, PATCH and DELETE;
- header and cookie bindings;
- `Mcp-Param` headers (`mcp_param_headers`);
- REST status codes, 204, 401/403, bodies that are not UTF-8, and bodies over the limit;
- streaming, and server-sent events;
- method precedence.

`trace_context_extraction` and `server_discovery_cache_config` are on.

**Cases.** There are 157, in [`rest_cases.py`](rest_cases.py):

| Area | Cases | What |
|---|---|---|
| `tools-list` | 7 | Both modes, legacy, order, invalid cursor |
| `sdk` | 19 | The SDK lists tools, calls them, uses `Mcp-Param` headers, discovers (`mode="auto"`), and surfaces errors |
| `versioning` | 11 | Unsupported versions (-32022), legacy versions and headers, a header without a `_meta` version |
| `lifecycle` | 23 | `server/discover`; `initialize` and `notifications/initialized` (2026-07-28 and legacy); no handshake; `Mcp-Session-Id`; GET and DELETE; removed and unknown methods |
| `headers` | 28 | `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name`: missing, wrong, duplicated, case, Base64. The header error comes before 404. |
| `params` | 18 | `Mcp-Param-*`: match, missing, unexpected, null, duplicate, invalid characters, Base64, numeric integers, booleans, legacy |
| `transcoding` | 16 | Request mapping (path, query, body, bindings, methods, trace context) and response mapping (text, streaming, events) |
| `errors` | 33 | REST errors (tool execution errors), invalid arguments, JSON-RPC errors (parse, batch, id, `jsonrpc`), notifications, body limits |
| `capabilities` | 2 | Required client capabilities |

Some SDK cases isolate functions from tools/list, so that a tools/list failure doesn't hide them:
- `sdk.call-tool-direct` sends tools/call through the SDK's session without the implicit
  tools/list that `Client.call_tool` makes.
- `sdk.mcp-param-encoding` sends the `Mcp-Param` headers that the SDK's own encoder makes.

The SDK cases that do depend on tools/list report its gap.

## Regression, compliance and diagnostic checks

A check either passes or fails, and it names the requirement that it checks:
- **A regression check** (no gap) must pass. A failure fails the run (exit 1).
- **A compliance check** names a known gap (`gap="G2"`). It fails on the current Envoy, for that
  reason, and its failure does not fail the run. With `COMPLIANCE=strict`, it does.
- **A known gap's check that passes** (`FIXED`) fails the run: the gap is fixed, so remove `gap=`
  from the check, and it guards against a regression from then on. `../verify.sh` reports such
  checks without failing, since Envoy's `dev` image, which it tests, moves on: it fails only when
  the run has a regression failure (or, with `COMPLIANCE=strict`, a known gap's failing check), or
  when Envoy or the REST server stopped.
- **A diagnostic check** names a diagnostic (`diagnostic="G9"`). It records how the bridge alone
  (listener B) behaves where the MCP filter in front of it meets the requirement in the supported
  chain (listener C), which regression checks on C verify. It is reported, with its evidence, but
  it is not an endpoint compliance failure, and it never fails the run, even with
  `COMPLIANCE=strict`.

The known gaps on Envoy's current `dev` image are below. The authoritative list, with what happens
and where in the code, is `KNOWN_GAPS` in [`requirements.py`](requirements.py).

| Gap | What the bridge does | Requirement | Checks |
|---|---|---|---|
| G2 | tools/list from the REST backend is passed through as is: no `resultType`, `ttlMs` or `cacheScope` | MUST | 7 |
| G6 | An unsupported legacy version gets HTTP 200, not 400 (bridge alone) | MUST | 1 |
| G7 | A notification that the bridge does not accept gets a JSON-RPC error with HTTP 200 | MUST | 2 |
| G8 | An error for an unreadable id has `"id": null`, not no `id` | MUST | 7 |
| G10 | Input validation errors are protocol errors (-32602), not results with `isError` | SHOULD | 5 |
| G11 | With two methods set, the first (get) is used, not the highest field number (post) | CONTRACT | 1 |
| G12 | Results have no `_meta` `serverInfo` (only discover's do) | SHOULD | 3 |
| G13 | Error code -32000, from the legacy range | SHOULD | 2 |
| G14 | An invalid tools/list cursor is ignored | SHOULD | 1 |

The diagnostics are below. The authoritative list is `DIAGNOSTICS` in
[`requirements.py`](requirements.py).

| Diagnostic | The bridge alone (B) | The supported chain (C), regression checks | Checks |
|---|---|---|---|
| G9 | Does not check `jsonrpc`: a request without it, or with `"1.0"`, is served | The MCP filter (`REJECT_NO_MCP`) rejects it with HTTP 400 before the bridge; the REST backend gets nothing (`errors.jsonrpc-missing@C`, `errors.jsonrpc-version@C`) | 2 |

G9 was a known gap until the MCP filter was found to reject these requests in the supported chain.
The MCP filter's 400 is `text/plain`, not a JSON-RPC error (-32600): the C cases print a `note` with
the body that they get.

**Outside this suite's scope.** On listener C, the MCP filter answers some header errors (for
example a missing `Mcp-Method`) with `"id": null` although the request's id was readable. The
cases do not check the MCP filter's ids, which [`../mcp_client.py`](../mcp_client.py) checks, but
they print a `note` for each such answer.

## Run with Docker Compose

[`docker-compose.yaml`](docker-compose.yaml) runs three containers:
- `rest-client`, the SDK and raw HTTP, which waits for `docker compose exec` to run the test in it;
- `envoy`, built from `envoyproxy/envoy:dev` with [`envoy.yaml`](envoy.yaml), as for the MCP
  backend;
- `rest-server`, built from `../docker`.

`../verify.sh` runs this test after the MCP backend's. By hand, with rootless Podman, first do step
1 of the [Rootless Podman Quick Start](../README.md#rootless-podman-quick-start). Then, from this
directory:

```sh
docker compose up --build -d
docker compose exec rest-client python -u docker/client_entrypoint.py
# Again, for one case, or the cases whose names start with a prefix: each run needs services that
# have just started, because the server clears the run directory when it starts.
docker compose up -d --force-recreate
docker compose exec -e ONLY=headers.,lifecycle.discover@B \
  rest-client python -u docker/client_entrypoint.py
docker compose down -v  # deletes the run volume, with the results; down keeps it
```

`docker compose exec` returns the client's exit code. It prints `PASS` when no regression check
fails, even if known gaps' or diagnostic checks do.

| Variable | Default | |
|---|---|---|
| `ENVOY_IMAGE`, `ENVOY_VARIANT` | `envoyproxy/envoy`, `dev` | The image that Envoy's is built from, as for the MCP backend: see [The Envoy image](../README.md#the-envoy-image) |
| `ONLY` | unset | Comma-separated case names or name prefixes to run |
| `SKIP_CASES` | unset | Comma-separated case names or name prefixes not to run |
| `COMPLIANCE` | unset | `strict`: known gaps' failing checks fail the run too |
| `LOG_LEVEL` | `info` | Envoy's log level; the bridge, the MCP filter and the router always log at debug |
| `RUN_DIR` | the `run` volume | A host directory for the run directory, as for `../docker-compose.yaml` |

`docker compose up` applies them when it creates the containers. `ONLY`, `SKIP_CASES` and
`COMPLIANCE` also work with `docker compose exec -e`, on services that have just started.

Envoy runs as the image's non-root `envoy` user. [`docker/server_entrypoint.sh`](docker/server_entrypoint.sh),
which runs before Envoy starts, makes the shared run directory writable for it, so that Envoy can
write its access log and its own log there.

## Results and failure reports

**Console.** The client prints one line per check:
- `ok` for a pass;
- `FAIL` for a regression failure;
- `GAP G<n>` for a known gap's failing check;
- `FIXED` for a known gap's check that now passes;
- `DIAG G<n>` for a diagnostic check that deviates from its requirement, and `diag` for one that
  meets it;
- `note` for an observation that is not a check.

Then it prints:
- a summary, with the checks per gap;
- every regression failure in full;
- each known gap with its failing checks;
- each diagnostic with its deviating checks.

**Run directory.** The run directory (`/e2e-run`) has:
- `report.txt`: every failure and diagnostic deviation in full.
- `results.json`: every case, check, exchange and log entry, for tooling.
- `client_output.txt`: the console output.
- `access.log`: Envoy's access log, one JSON object per request. It includes the REST method and
  path after transcoding, `response_code_details`, both filters' dynamic metadata, and the
  connection id.
- `envoy.log`: Envoy's log, with the debug lines of the bridge, the MCP filter and the router.
- `rest_requests.jsonl`: every request that reached the REST backend, with its raw path, query,
  headers and body.
- `server_info.json`: Envoy's admin `/server_info`.

To copy it out of the volume:

```sh
docker cp "$(docker compose ps -aq rest-client)":/e2e-run/. /tmp/rest-e2e-run
```

**A failure in full.** Each failure lists:
- the test and check, the expected behavior, and the requirement with its level and source;
- the actual result;
- the suspected gap, the diagnostic, or "none known" for a regression or a new gap;
- each HTTP exchange: the request as sent, and the response's status, headers and body (or
  `no response in 5s`, or `body incomplete after 3s: 0 of 23 bytes`);
- the SDK's exception (type, code, message, data);
- the case's Envoy access log entries, and the Envoy debug lines of their connections;
- the REST backend's requests;
- how to reproduce it.

Every request carries an `X-E2E-Case` header with the case's name, which the bridge forwards to the
backend: that is how the client finds a case's log entries.

## The Envoy image

Envoy is built from `envoyproxy/envoy:dev`, as for the MCP backend: see
[The Envoy image](../README.md#the-envoy-image), and `ENVOY_IMAGE` and `ENVOY_VARIANT` to test
another image. The `dev` tag follows Envoy's `main` branch. The suite needs:
- the bridge's 2026-07-28 support: envoyproxy/envoy#47473 (`resultType`), #47817
  (`server/discover`), #47878 (`Mcp-Param` headers) and #48308 (404 for unsupported methods);
- the fixes of the former known gaps: #48125 (G1, cache hints of a local tools/list), #48638 (G3,
  the 405's body), #48635 (G4, an empty POST), #48299 (G5, client capabilities), #48720 (G6, a
  2026-07-28 header without a `_meta` version) and #48744 (G15, a streamed headers-only response);
- the MCP filter's #47280, #47862, #47915 and #48720.

An image of an older commit (`ENVOY_VARIANT=dev-<commit>`) must contain them all. In an Envoy
checkout, with `COMMIT` the image's commit:

```sh
for c in bfd41cd54d81cad5975b0443ab9c59543f1bbe18 f15dbecafda74aab1c88209bb59a0428e8e30e87 \
    35ef062c73bdadd2cb64a3837e54dcb0f490e34b 545d4a58abc84c5cb92966e8281689c988a35edb \
    462a53dfe63b215829060f43aac215c5f57808c8 a887bcc47fad0d451d5b9c658b629c12800982ea \
    eb32f1f93e91d651129470c44811ad908ba7bb41 1a888a2bf8c40af10e8c6d573d83301230e506b8 \
    61a17ea4482baaaee0ea5579e57c80f40e9c3c0f 7d393e789019c0642c2af6a1cb02e72ce6b1ba5a \
    36cfbfb5d1795326561aaee5a4796e83407fc494 a635b18e52d7263e79e00c9420eeb5d77eff5363 \
    5af8d913a34f6e71b6c6cf482ddf8d4b406df533; do
  git merge-base --is-ancestor "$c" "$COMMIT" && echo "ok      $c" || echo "MISSING $c"
done
```

A run against a newer image must have no regression failure. Expect `FIXED` lines for the gaps
that it fixes: remove those gaps from their checks.

## Changing the suite

- **A new case.** Add it to `rest_cases.py` with `@case(name, area, what, listeners)`.
  - Cite a requirement of `requirements.py` in each check, and add the requirement there first if it
    is new, with its source.
  - Take expected REST answers from `rest_server.route`, through `rest_answer`.
- **A new gap.** When a check fails, first confirm the expectation against its source. Then:
  - add the gap to `KNOWN_GAPS`, with what happens and where;
  - name it on the failing checks only;
  - leave the expectation as it is.
- **A fixed gap.** Remove `gap=` from the checks that report `FIXED`. Remove the gap from
  `KNOWN_GAPS` when no check names it.

## Files

| File | What |
|---|---|
| [`envoy.yaml`](envoy.yaml) | The Envoy config, which the `envoy` service's image has as `/etc/envoy.yaml`: listeners C and B, the shared tools, the access log |
| [`rest_server.py`](rest_server.py) | The REST backend: deterministic answers, raw-path routing, streaming, and the request log |
| [`requirements.py`](requirements.py) | The requirements that checks cite, and the known gaps |
| [`rest_cases.py`](rest_cases.py) | The cases |
| [`rest_client.py`](rest_client.py) | The runner: raw HTTP, SDK sessions, log correlation, reports |
| [`docker-compose.yaml`](docker-compose.yaml), [`docker/`](docker) | The Docker Compose setup, the server's entrypoint, and the client's test run |
