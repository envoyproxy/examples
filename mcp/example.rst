.. _install_sandboxes_mcp:

MCP filter and MCP JSON-REST bridge
===================================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

This sandbox puts Envoy in front of two Model Context Protocol (MCP) backends, and tests it with
real MCP clients, at MCP protocol version ``2026-07-28``. Each backend is a Docker Compose project of
its own:

- **The MCP backend**: an MCP server, behind Envoy's :ref:`MCP filter <config_http_filters_mcp>`.
  The filter parses the JSON-RPC body of each request. For ``2026-07-28``, it checks the
  ``Mcp-Method`` and ``Mcp-Name`` headers against the body, and the protocol version and the client
  capabilities in ``params._meta``, and answers a request that breaks these rules itself.
- **The REST backend**: a plain REST service, behind the
  :ref:`MCP JSON-REST bridge <envoy_v3_api_msg_extensions.filters.http.mcp_json_rest_bridge.v3.McpJsonRestBridge>`,
  which serves the service's REST endpoints as MCP tools. One listener has the MCP filter in front
  of the bridge, and another has the bridge alone.

The MCP server and the clients are built on the official MCP Python SDK, ``mcp`` 2.2.0. Each client
runs a suite of cases through Envoy, with the SDK and with raw HTTP requests. For each request, it
checks the answer, Envoy's access log, the filters' dynamic metadata and statistics, and what reached
the backend.

The sandbox publishes no ports: the clients run in their containers, with ``docker compose exec``.

.. warning::

   The MCP JSON-REST bridge's API is a work in progress.

Step 1: Start the MCP backend
*****************************

Change to the ``mcp`` directory, and build and start the MCP server, Envoy and the MCP client.

.. code-block:: console

   $ pwd
   examples/mcp
   $ docker compose up --build -d
   $ docker compose ps
   NAME                   IMAGE                            COMMAND                  SERVICE      CREATED          STATUS                    PORTS
   mcp-e2e-envoy-1        mcp-e2e-envoy                    "/docker-entrypoint.…"   envoy        13 seconds ago   Up 10 seconds (healthy)   10000/tcp
   mcp-e2e-mcp-client-1   envoy-mcp-e2e-python:mcp-2.2.0   "sleep infinity"         mcp-client   13 seconds ago   Up 9 seconds
   mcp-e2e-mcp-server-1   envoy-mcp-e2e-python:mcp-2.2.0   "sh docker/server_en…"   mcp-server   13 seconds ago   Up 12 seconds (healthy)

Envoy listens on port ``10000``, and on port ``10001``, whose MCP filter supports protocol versions
up to ``2025-11-25`` only. Both forward to the MCP server:

.. literalinclude:: _include/mcp/envoy.yaml
   :language: yaml
   :lines: 67-80
   :linenos:
   :lineno-start: 67
   :caption: :download:`envoy.yaml <_include/mcp/envoy.yaml>`

Step 2: Run the MCP backend's cases
***********************************

The MCP client runs 17 cases. With the SDK, it lists the tools and calls one, through the first
listener, and lists the tools through the second, whose MCP filter answers with error ``-32022``
itself. With raw HTTP, it sends requests that each break one ``2026-07-28`` rule, which the MCP
filter must answer without forwarding them, and a few that it must forward.

.. code-block:: console

   $ docker compose exec mcp-client python -u docker/client_entrypoint.py
   ==> Envoy 363c84b1e96438fcd055056e27041f4e3b517e8d/1.41.0-dev/Clean/RELEASE/BoringSSL, at envoy:10000, in front of the MCP server at mcp-server:8000

   MCP Python SDK 2.2.0, protocol version 2026-07-28, through Envoy at envoy:10000, and at envoy:10001 capped at 2025-11-25
   ...
   [missing-mcp-method] tools/list without the Mcp-Method header
     ok    400, application/json: {"jsonrpc": "2.0", "id": null, "error": {"code": -32020, "message": "Missing required Mcp-Method header"}} (got 400, ...)
     ok    the request did not reach the server (got [])
     ok    MCP filter counters: header_mismatch +1, others unchanged (got header_mismatch +1, others unchanged)
     ok    access log: Envoy answered 400 itself, with no upstream host (got 400 from None)
     ok    access log: the MCP filter's metadata has status mcp_not_jsonrpc, is_mcp_request false (got ...)
   ...
   Cases: 17 of 17 run, 17 passed, 0 failed

   Processes
     ok    Envoy is still running
     ok    The MCP server is still running

   PASS. Logs and files: the run directory, /e2e-run, in the mcp-client container (see README.md)

Each check prints ``ok`` or ``FAIL``, and any ``FAIL`` fails the run.

Step 3: Run the developer demo
******************************

The demo walks through ``2026-07-28`` with a simulated service-operations scenario, whose tools the
MCP server has with ``DEMO=1``. It also shows ``server/discover``, cache hints and a multi
round-trip request, which the SDK and the MCP server handle, and which Envoy forwards.

Restart the services in demo mode, and run the demo:

.. code-block:: console

   $ DEMO=1 docker compose up -d --force-recreate
   $ docker compose exec mcp-client python -u docker/client_entrypoint.py
   ...
    9. Final Summary
   ====================================================================================================
       ✓ 1. MCP 2026-07-28 Connection: 2 of 2 checks passed
       ✓ 2. Tool Discovery: 2 of 2 checks passed
       ✓ 3. Multi-step Tool Execution: 5 of 5 checks passed
       ✓ 4. Stateless Request Metadata: 4 of 4 checks passed
       ✓ 5. Header Validation (Envoy MCP filter): 6 of 6 checks passed
       ✓ 6. Protocol Version Enforcement (Envoy MCP filter): 3 of 3 checks passed
       ✓ 7. Client Capabilities Validation (Envoy MCP filter): 2 of 2 checks passed
       ✓ 8. Optional Advanced Features (SDK client and MCP backend; Envoy forwards): 5 of 5 checks passed

       Envoy logged 24 demo requests: it forwarded 16 to the MCP backend, and answered 8 itself.
   ...
       Demo checks: 31 of 31 passed
   ...
   PASS. Logs and files: the run directory, /e2e-run, in the mcp-client container (see README.md)

``--force-recreate`` restarts all three services, in order: the MCP server clears the shared run
directory, so Envoy has to start after it, to open a new access log.

Step 4: Start the REST backend
******************************

Change to the ``rest_backend`` directory, and build and start the REST service, Envoy and the
client.

.. code-block:: console

   $ cd rest_backend
   $ docker compose up --build -d

Envoy listens on port ``10000``, with the MCP filter in front of the bridge, the chain that the
cases treat as supported, and on port ``10001``, with the bridge alone. Both have the same sixteen
tools, which the bridge transcodes to REST requests:

.. literalinclude:: _include/mcp/rest_backend/envoy.yaml
   :language: yaml
   :lines: 74-95
   :linenos:
   :lineno-start: 74
   :caption: :download:`rest_backend/envoy.yaml <_include/mcp/rest_backend/envoy.yaml>`

Step 5: Run the REST backend's cases
************************************

The client runs 157 cases: tools/list in both of the bridge's modes, the SDK, protocol versions,
the lifecycle, the MCP headers and ``Mcp-Param`` headers, the REST transcoding, and errors.

.. code-block:: console

   $ docker compose exec rest-client python -u docker/client_entrypoint.py
   ==> Envoy 363c84b1e96438fcd055056e27041f4e3b517e8d/1.41.0-dev/Clean/RELEASE/BoringSSL: listener C at envoy:10000 (MCP filter, bridge), listener B at envoy:10001 (bridge), in front of the REST backend at rest-server:8000

   [tools-list.local@B] 2026-07-28 tools/list, answered by the bridge (tool_list_local)
     ok    HTTP 200 (HTTP-JSON-RESPONSE)
     ok    Content-Type application/json (HTTP-JSON-RESPONSE)
   ...
   ====================================================================================================
   Envoy 363c84b1e96438fcd055056e27041f4e3b517e8d/1.41.0-dev/Clean/RELEASE/BoringSSL
   Cases: 157 run, 0 not selected
   Regression checks: 851 passed, 0 failed
   Compliance checks (known gaps): 29 failing as known, 0 now passing
     G2   tools/list from the REST backend is passed through as is: 7 checks (MUST, SDK)
   ...
   PASS. Logs and files: the run directory, /e2e-run, in the rest-client container (see README.md)

Each check cites the requirement that it checks, from the MCP specification or the bridge's API:

- A **regression check** must pass: a failure fails the run.
- A **compliance check** names a known gap, a requirement that Envoy does not meet yet. Its failure
  is reported (``GAP``), and fails the run only with ``COMPLIANCE=strict``.
- When a known gap's check passes (``FIXED``), the client fails the run, so that the gap gets removed
  from the check. The sandbox's ``verify.sh`` reports it without failing, because Envoy's ``dev``
  image moves on.

Each run of the cases needs services that have just started: the server clears the run directory
when it starts, and the checks expect the logs of one run only. To run only some cases, restart the
services, and give the cases' names, or prefixes of them, in ``ONLY``:

.. code-block:: console

   $ docker compose up -d --force-recreate
   $ docker compose exec -e ONLY=headers.,lifecycle.discover@B rest-client python -u docker/client_entrypoint.py

Step 6: Read the reports
************************

Each backend's services share a run directory, with Envoy's access log, the backend's request log
and the client's output. The REST client also writes every failure in full, with its HTTP exchanges
and log entries, to ``report.txt``, and all of its results to ``results.json``:

.. code-block:: console

   $ docker compose exec rest-client ls /e2e-run
   access.log  client_output.txt  envoy.log  report.txt  rest_requests.jsonl  results.json  server_info.json
   $ docker compose cp rest-client:/e2e-run/report.txt .

Step 7: Stop the backends
*************************

.. code-block:: console

   $ docker compose down -v
   $ cd ..
   $ docker compose down -v

.. seealso::

   :ref:`MCP filter <config_http_filters_mcp>`
      Learn more about the MCP filter.

   :ref:`MCP JSON-REST bridge API <envoy_v3_api_msg_extensions.filters.http.mcp_json_rest_bridge.v3.McpJsonRestBridge>`
      The MCP JSON-REST bridge's configuration.

   `MCP specification, 2026-07-28 <https://modelcontextprotocol.io/specification/2026-07-28>`_
      The version of the Model Context Protocol that the sandbox uses.

   `The sandbox's README <https://github.com/envoyproxy/examples/blob/main/mcp/README.md>`_
      The cases, the known gaps, and how to change the suites.
