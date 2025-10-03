.. _install_sandboxes_reverse_tunnel:

Reverse Tunnels
===============

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

This sandbox demonstrates Envoy's :ref:`reverse tunnels <config_reverse_connection>` feature, which allows establishing
long-lived connections from downstream to upstream in scenarios where direct connectivity from upstream to downstream
is not possible, and using these cached connection sockets to send data traffic from upstream to downstream Envoy.

In this example, a downstream Envoy proxy initiates reverse tunnels to an upstream Envoy using a custom address resolver. The configuration includes bootstrap extensions and reverse connection listeners with specialized address formats.

Step 1: Build Envoy with reverse tunnels feature
************************************************

Build Envoy with the reverse tunnels feature enabled:

.. code-block:: console

  $ ./ci/run_envoy_docker.sh './ci/do_ci.sh bazel.release.server_only'

Step 2: Build Envoy Docker image
********************************

Build the Envoy Docker image and tag it as ``debug/envoy:latest``.

.. code-block:: console

  $ ENVOY_DOCKER_IN_DOCKER=1 ./ci/run_envoy_docker.sh './ci/do_ci.sh docker'

Verify the built images:

.. code-block:: console

  $ docker image ls

Expected output showing the built Envoy images:

.. code-block:: console

  REPOSITORY                      TAG                                        IMAGE ID       CREATED              SIZE
  envoyproxy/envoy                dev-57894704c2fc60ead4818d8d77e7ec7fa   abc8392a56c4   2 minutes ago        193MB

Tag the development image as ``debug/envoy:latest`` for use in the sandbox:

.. code-block:: console

  $ docker tag envoyproxy/envoy:dev-57894704c2fc60ead4818d8d77e7ec7fa debug/envoy:latest

Step 3: Understanding the configuration
**************************************

The reverse tunnel configuration is explained in the :ref:`Reverse Tunnels <config_reverse_connection>` section.

Step 4: Launch test containers
******************************

Change to the ``reverse_tunnel`` directory and bring up the docker composition.

.. code-block:: console

  $ pwd
  examples/reverse_tunnel
  $ docker compose up

.. note::
   The docker-compose maps the following ports:

   - **downstream-envoy**: Host port 9000 → Container port 9000 (reverse connection API)
   - **upstream-envoy**: Host port 9001 → Container port 9000 (reverse connection API)

Verify the containers are running:

.. code-block:: console

  $ docker ps

Expected output showing all containers are up:

.. code-block:: console

  CONTAINER ID   IMAGE                         COMMAND                  CREATED          STATUS         NAMES
  ae15eab504f8   debug/envoy:latest            "/docker-entrypoint.…"   27 seconds ago   Up 3 seconds   reverse_tunnel-downstream-envoy-1
  58eba3678f20   nginxdemos/hello:plain-text   "/docker-entrypoint.…"   27 seconds ago   Up 3 seconds   reverse_tunnel-downstream-service-1
  49145cc8a9d1   debug/envoy:latest            "/docker-entrypoint.…"   27 seconds ago   Up 3 seconds   reverse_tunnel-upstream-envoy-1

Step 5: Validate reverse tunnel establishment
*********************************************

Verify that reverse tunnels have been successfully established by checking the stats counters on both downstream and upstream Envoy proxies.

Check downstream Envoy stats (port 8888):

.. code-block:: console

  $ curl http://localhost:8888/stats | grep reverse_connection

Expected downstream stats showing connected reverse tunnels:

.. code-block:: console

  downstream_reverse_connection.cluster.upstream-cluster.connected: 1
  downstream_reverse_connection.cluster.upstream-cluster.connecting: 0
  downstream_reverse_connection.host.172.27.0.2:9000.connected: 1
  downstream_reverse_connection.host.172.27.0.2:9000.connecting: 0
  downstream_reverse_connection.worker_0.cluster.upstream-cluster.connected: 1
  downstream_reverse_connection.worker_0.cluster.upstream-cluster.connecting: 0
  downstream_reverse_connection.worker_0.host.172.27.0.2:9000.connected: 1
  downstream_reverse_connection.worker_0.host.172.27.0.2:9000.connecting: 0

Check upstream Envoy stats (port 8889):

.. code-block:: console

  $ curl http://localhost:8889/stats | grep reverse_connections

Expected upstream stats showing received reverse connections:

.. code-block:: console

  reverse_connections.clusters.downstream-cluster: 1
  reverse_connections.nodes.downstream-node: 1
  reverse_connections.worker_0.cluster.downstream-cluster: 1
  reverse_connections.worker_0.node.downstream-node: 1

The stats confirm that:

- **Downstream Envoy**: Has successfully connected (``connected: 1``) to the upstream cluster
  with no pending connections (``connecting: 0``)
- **Upstream Envoy**: Has received reverse connections from the downstream node and cluster,
  as indicated by the reverse connection counters

Step 6: Test reverse tunnel
***************************

Perform HTTP requests for the service behind downstream Envoy, to upstream Envoy.
These requests will be sent over a reverse tunnel. You can route requests using either
cluster ID or node ID headers.

**Option 1: Route by cluster ID**

.. code-block:: console

  $ curl -H "x-cluster-id: downstream-cluster" http://localhost:8085/downstream_service -v

Expected response:

.. code-block:: console

  *   Trying ::1...
  * TCP_NODELAY set
  * Connected to localhost (::1) port 8085 (#0)
  >GET /downstream_service HTTP/1.1
  >Host: localhost:8085
  >User-Agent: curl/7.61.1
  >Accept: */*
  >x-cluster-id: downstream-cluster
  >
  <HTTP/1.1 200 OK
  <server: envoy
  <date: Thu, 02 Oct 2025 23:47:18 GMT
  <content-type: text/plain
  <content-length: 159
  <expires: Thu, 02 Oct 2025 23:47:17 GMT
  <cache-control: no-cache
  <x-envoy-upstream-service-time: 13
  <
  Server address: 172.31.0.3:80
  Server name: 90dde65fa099
  Date: 02/Oct/2025:23:47:18 +0000
  URI: /downstream_service
  Request ID: db89e5aa9fb485d5f1749f537240ad9d
  * Connection #0 to host localhost left intact

**Option 2: Route by node ID**

.. code-block:: console

  $ curl -H "x-node-id: downstream-node" http://localhost:8085/downstream_service -v

Expected response:

.. code-block:: console

  *   Trying ::1...
  * TCP_NODELAY set
  * Connected to localhost (::1) port 8085 (#0)
  >GET /downstream_service HTTP/1.1
  >Host: localhost:8085
  >User-Agent: curl/7.61.1
  >Accept: */*
  >x-node-id: downstream-node
  >
  <HTTP/1.1 200 OK
  <server: envoy
  <date: Thu, 02 Oct 2025 23:48:17 GMT
  <content-type: text/plain
  <content-length: 159
  <expires: Thu, 02 Oct 2025 23:48:16 GMT
  <cache-control: no-cache
  <x-envoy-upstream-service-time: 4
  <
  Server address: 172.31.0.3:80
  Server name: 90dde65fa099
  Date: 02/Oct/2025:23:48:17 +0000
  URI: /downstream_service
  Request ID: 31657da3c832fb66dbc1990a8c18b828
  * Connection #0 to host localhost left intact

Both routing methods demonstrate that the reverse tunnel is working correctly,
with requests being successfully routed from upstream Envoy to the downstream service
over the established reverse connection.

.. seealso::

   :ref:`Reverse Tunnels architecture overview <config_reverse_connection>`
      Learn more about Envoy's reverse tunnel functionality.
