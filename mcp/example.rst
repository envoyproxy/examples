.. _install_sandboxes_mcp:

MCP filter and MCP JSON-REST bridge
===================================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

   :ref:`jq <start_sandboxes_setup_jq>`
        Parse JSON output from the proxy.

This sandbox serves a REST API as a Model Context Protocol (MCP) server, at MCP protocol version
``2026-07-28``: MCP clients send JSON-RPC requests to Envoy, and Envoy turns their tool calls into
REST requests.

The REST API is a local mock of a small weather and orders service. In front of it, Envoy runs two
filters:

- The :ref:`MCP filter <config_http_filters_mcp>` parses the JSON-RPC body of each request, and
  rejects requests that are not MCP. At protocol version ``2026-07-28``, it also checks the
  ``Mcp-Method`` and ``Mcp-Name`` headers against the body, and that ``params._meta`` has the
  protocol version and the client capabilities. It stores what it parsed as
  :ref:`dynamic metadata <config_http_filters_mcp_dynamic_metadata>`.
- The :ref:`MCP JSON-REST bridge <envoy_v3_api_msg_extensions.filters.http.mcp_json_rest_bridge.v3.McpJsonRestBridge>`
  serves the REST API as MCP tools. It answers ``server/discover`` and ``tools/list`` itself, from
  its configuration, and transcodes each ``tools/call`` into a REST request, and the REST response
  into the tool's result.

The MCP filter does not need the bridge: it can also sit on its own in front of a native MCP server.

.. warning::

   The MCP filter and the MCP JSON-REST bridge are not in an Envoy release yet: the sandbox needs an
   Envoy build from ``main``, such as the ``envoyproxy/envoy:dev`` image that it uses. Their APIs are
   a work in progress, and Envoy logs warnings about them at startup.

Step 1: Start the sandbox
*************************

Change to the ``mcp`` directory, and build and start the proxy and the REST API.

.. code-block:: console

   $ pwd
   examples/mcp
   $ docker compose pull
   $ docker compose up --build -d
   $ docker compose ps
   NAME          IMAGE       COMMAND                  SERVICE   CREATED          STATUS                    PORTS
   mcp-proxy-1   mcp-proxy   "/docker-entrypoint.…"   proxy     10 seconds ago   Up 4 seconds (healthy)    0.0.0.0:9901->9901/tcp, 0.0.0.0:10000->10000/tcp
   mcp-rest-1    mcp-rest    "python3 /code/servi…"   rest      10 seconds ago   Up 9 seconds (healthy)

Envoy listens for MCP requests on port ``10000``, and serves its admin interface on port ``9901``.
The configuration of the MCP filter and the bridge, and the tools that the bridge serves:

.. literalinclude:: _include/mcp/envoy.yaml
   :language: yaml
   :lines: 41-93
   :linenos:
   :lineno-start: 41
   :caption: :download:`envoy.yaml <_include/mcp/envoy.yaml>`

Step 2: Discover the server
***************************

An MCP ``2026-07-28`` request is a JSON-RPC ``POST``, whose ``params._meta`` has the protocol
version, the client's information and its capabilities. Its headers repeat the protocol version and
the method. There is no ``initialize`` handshake: a client asks the server what it supports with
``server/discover``:

.. code-block:: bash

   curl -s http://localhost:10000/mcp \
     -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
     -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: server/discover' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                     "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
                     "io.modelcontextprotocol/clientCapabilities": {}}}}' \
     | jq '.result'

.. code-block:: json

   {
     "_meta": {
       "io.modelcontextprotocol/serverInfo": {
         "name": "localhost",
         "version": "1.0.0"
       }
     },
     "cacheScope": "public",
     "capabilities": {
       "tools": {
         "listChanged": false
       }
     },
     "resultType": "complete",
     "supportedVersions": [
       "2024-11-05",
       "2025-03-26",
       "2025-06-18",
       "2025-11-25",
       "2026-07-28"
     ],
     "ttlMs": 0
   }

The bridge answered itself: the request never reached the REST API. The bridge has no setting for the
server's name: ``serverInfo`` has the host of the request's ``Host`` header, ``localhost``, and the
version ``1.0.0``.

Step 3: List the tools
**********************

The bridge also answers ``tools/list`` itself, with the tools of its configuration:

.. code-block:: bash

   curl -s http://localhost:10000/mcp \
     -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
     -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/list' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                     "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
                     "io.modelcontextprotocol/clientCapabilities": {}}}}' \
     | jq -c '.result.tools[] | {name, title, description}'

.. code-block:: json

   {"name":"get_weather","title":"Weather","description":"The current weather in a city."}
   {"name":"create_order","title":"Create an order","description":"Creates an order for an item."}
   {"name":"stream_text","title":"Stream text","description":"Streams an answer in several parts."}

Step 4: Call a tool that is a GET request
*****************************************

Call ``get_weather``. A ``tools/call`` request also needs the ``Mcp-Name`` header, with the tool's
name:

.. code-block:: bash

   curl -s http://localhost:10000/mcp \
     -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
     -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/call' -H 'mcp-name: get_weather' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
           "name": "get_weather", "arguments": {"city": "Paris", "units": "imperial"},
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                     "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
                     "io.modelcontextprotocol/clientCapabilities": {}}}}' \
     | jq '.result'

.. code-block:: json

   {
     "content": [
       {
         "text": "{\"city\": \"Paris\", \"conditions\": \"sunny\", \"temperature\": 72, \"units\": \"imperial\"}",
         "type": "text"
       }
     ],
     "isError": false,
     "resultType": "complete"
   }

The bridge sent ``GET /v1/weather/Paris?units=imperial`` to the REST API: ``city`` filled the
``{city}`` variable of the tool's path, and ``units``, which is not in the path, became a query
parameter. The REST API's JSON answer is the text content of the tool's result.

Step 5: Call a tool that is a POST request
******************************************

``create_order`` is a ``POST`` with ``body: "*"``: the bridge sends the arguments as the JSON body.
The REST API echoes the order that it received:

.. code-block:: bash

   curl -s http://localhost:10000/mcp \
     -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
     -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/call' -H 'mcp-name: create_order' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
           "name": "create_order", "arguments": {"item": "widget", "quantity": 3},
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                     "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
                     "io.modelcontextprotocol/clientCapabilities": {}}}}' \
     | jq -r '.result.content[0].text'

.. code-block:: json

   {"id": "order-1", "status": "created", "order": {"item": "widget", "quantity": 3}}

Step 6: Stream a tool's result
******************************

The REST API answers ``stream_text`` with a stream of server-sent events. With
``text_content_streaming_enabled``, the bridge streams the tool's result to the client in a chunked
``application/json`` response, with each event as a text item, as the events arrive. The client gets
a JSON-RPC response, not server-sent events:

.. code-block:: bash

   curl -sN http://localhost:10000/mcp \
     -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
     -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/call' -H 'mcp-name: stream_text' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
           "name": "stream_text", "arguments": {},
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                     "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
                     "io.modelcontextprotocol/clientCapabilities": {}}}}' \
     | jq -c '.result.content[]'

.. code-block:: json

   {"type":"text","text":"The REST API sends"}
   {"type":"text","text":"this answer"}
   {"type":"text","text":"in three events."}

Step 7: Get a tool error
************************

The REST API answers ``404`` for a city that it does not know. The bridge turns the error into a
tool result with ``isError: true``, so that the client, or its model, can read it:

.. code-block:: bash

   curl -s http://localhost:10000/mcp \
     -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
     -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/call' -H 'mcp-name: get_weather' \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
           "name": "get_weather", "arguments": {"city": "Atlantis"},
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                     "io.modelcontextprotocol/clientInfo": {"name": "curl", "version": "1.0.0"},
                     "io.modelcontextprotocol/clientCapabilities": {}}}}' \
     | jq '.result'

.. code-block:: json

   {
     "content": [
       {
         "text": "{\"error\": \"No weather for Atlantis.\"}",
         "type": "text"
       }
     ],
     "isError": true,
     "resultType": "complete"
   }

Step 8: Send a request that is not MCP
**************************************

With ``traffic_mode: REJECT_NO_MCP``, the MCP filter answers a request that is not MCP itself, here
a JSON body that is not a JSON-RPC message, so that it reaches neither the bridge nor the REST API:

.. code-block:: console

   $ curl -s -w '\n%{http_code}\n' http://localhost:10000/mcp \
       -H 'content-type: application/json' \
       -d '{"city": "Paris"}'
   request must be a valid JSON-RPC 2.0 message for MCP
   400

Step 9: See what each request became
************************************

Envoy's access log shows, for each request, the MCP method and tool that the MCP filter read from the
JSON-RPC body, and the REST request that the bridge made of it:

.. code-block:: console

   $ docker compose logs proxy | grep -- ' -> '
   proxy-1  | server/discover - -> POST /mcp 200 mcp_json_rest_bridge_filter_server_discover
   proxy-1  | tools/list - -> POST /mcp 200 mcp_json_rest_bridge_tools_list
   proxy-1  | tools/call get_weather -> GET /v1/weather/Paris?units=imperial 200 via_upstream
   proxy-1  | tools/call create_order -> POST /v1/orders 200 via_upstream
   proxy-1  | tools/call stream_text -> GET /v1/stream/text 200 via_upstream
   proxy-1  | tools/call get_weather -> GET /v1/weather/Atlantis 200 via_upstream
   proxy-1  | - - -> POST /mcp 400 mcp_not_jsonrpc

The method and the tool are the MCP filter's dynamic metadata, read with
``%DYNAMIC_METADATA(envoy.filters.http.mcp:method)%`` and
``%DYNAMIC_METADATA(envoy.filters.http.mcp:params:name)%``. The method and the path are those of the
REST request, as the bridge rewrote them. The bridge answered ``server/discover`` and ``tools/list``
itself, and the MCP filter the request that was not MCP.

The status is the one that Envoy sent to the client: the bridge answered each tool call with a
``200``. The REST API created the order with a ``201``, and answered ``404`` for Atlantis, which the
bridge turned into a tool result with ``isError: true``.

.. seealso::

   :ref:`MCP filter <config_http_filters_mcp>`
      Learn more about the MCP filter, and its other uses, such as authorization on MCP attributes.

   :ref:`MCP filter dynamic metadata <config_http_filters_mcp_dynamic_metadata>`
      The attributes that the MCP filter stores for other filters and the access log.

   :ref:`MCP JSON-REST bridge API <envoy_v3_api_msg_extensions.filters.http.mcp_json_rest_bridge.v3.McpJsonRestBridge>`
      The MCP JSON-REST bridge's configuration.

   `MCP specification, 2026-07-28 <https://modelcontextprotocol.io/specification/2026-07-28>`_
      The version of the Model Context Protocol that the sandbox uses.
