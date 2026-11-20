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
checks the answer and what reached the backend. The MCP client also checks Envoy's access log, and
the MCP filter's dynamic metadata and statistics.

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
   ...
   [missing-mcp-method] tools/list without the Mcp-Method header
     ok    400, application/json: {"jsonrpc": "2.0", "id": null, "error": {"code": -32020, ...}} (got 400, ...)
     ok    the request did not reach the server (got [])
     ok    MCP filter counters: header_mismatch +1, others unchanged (got header_mismatch +1, others unchanged)
   ...
   Cases: 17 of 17 run, 17 passed, 0 failed
   ...
   PASS. Logs and files: the run directory, /e2e-run, in the mcp-client container (see README.md)

Each check prints ``ok`` or ``FAIL``, and any ``FAIL`` fails the run. Each run needs services that
have just started, because the MCP server clears the shared run directory when it starts: to run the
cases again, first run ``docker compose up -d --force-recreate``.

Step 3: Start the REST backend
******************************

Change to the ``rest_backend`` directory, and build and start the REST service, Envoy and the
client.

.. code-block:: console

   $ cd rest_backend
   $ docker compose up --build -d

Envoy listens on port ``10000``, with the MCP filter in front of the bridge, the chain that the
cases treat as supported, and on port ``10001``, with the bridge alone. Both have the same four
tools, which the bridge transcodes to REST requests:

.. literalinclude:: _include/mcp/rest_backend/envoy.yaml
   :language: yaml
   :lines: 71-88
   :linenos:
   :lineno-start: 71
   :caption: :download:`rest_backend/envoy.yaml <_include/mcp/rest_backend/envoy.yaml>`

Step 4: Run the REST backend's cases
************************************

The client runs 11 cases: tools/list in both of the bridge's modes, a tool call with the SDK,
``Mcp-Param`` headers, the transcoding of a GET, a POST and a streamed answer, and an empty POST.

.. code-block:: console

   $ docker compose exec rest-client python -u docker/client_entrypoint.py
   ...
   Cases: 11 run, 0 not selected
   Regression checks: 97 passed, 0 failed
   Compliance checks (known gaps): 7 failing as known, 0 now passing
   ...
   PASS. Logs and files: the run directory, /e2e-run, in the rest-client container (see README.md)

Each check cites the requirement that it checks, from the MCP specification or the bridge's API:

- A **regression check** must pass: a failure fails the run.
- A **compliance check** names a known gap, a requirement that Envoy does not meet yet. Its failure
  is reported (``GAP``), and does not fail the run.
- When a known gap's check passes (``FIXED``), the client warns that the gap should be removed from
  the check. That does not fail the run either, because Envoy's ``dev`` image moves on.

To run only some cases, restart the services, and give the cases' names, or prefixes of them, in
``ONLY``:

.. code-block:: console

   $ docker compose up -d --force-recreate
   $ docker compose exec -e ONLY=params.,tools-list.local@B rest-client python -u docker/client_entrypoint.py

Step 5: Read the logs
*********************

Each backend's services share a run directory, with Envoy's access log, the backend's request log
and the client's output:

.. code-block:: console

   $ docker compose exec rest-client ls /e2e-run
   access.log  client_output.txt  rest_requests.jsonl  server_info.json
   $ docker compose cp rest-client:/e2e-run/client_output.txt .

Step 6: Stop the backends
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
