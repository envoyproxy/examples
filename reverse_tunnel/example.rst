.. _install_sandboxes_reverse_tunnel:

Reverse Tunnels
===============

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

This sandbox demonstrates Envoy's :ref:`reverse tunnels <config_reverse_connection>` feature, which allows establishing long-lived connections from downstream to upstream in scenarios where direct connectivity from upstream to downstream is not possible, and using these cached connection sockets to send data traffic from upstream to downstream Envoy.

In this example, a downstream Envoy proxy initiates reverse tunnels to an upstream Envoy using a custom address resolver. The configuration includes bootstrap extensions and reverse connection listeners with specialized address formats.

Step 1: Build Envoy with reverse tunnels feature
************************************************

Build Envoy with the reverse tunnels feature enabled:

.. code-block:: console

  $ ./ci/run_envoy_docker.sh './ci/do_ci.sh bazel.release.server_only'

Step 2: Build Envoy Docker image
********************************

Build the Envoy Docker image:

.. code-block:: console

  $ docker build -f ci/Dockerfile-envoy-image -t envoy:latest .

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

  CONTAINER ID   IMAGE                         COMMAND                  CREATED          STATUS         PORTS                                                                                                                                        NAMES
  ae15eab504f8   debug/envoy:latest            "/docker-entrypoint.…"   27 seconds ago   Up 3 seconds   0.0.0.0:6060->6060/tcp, :::6060->6060/tcp, 0.0.0.0:8888->8888/tcp, :::8888->8888/tcp, 0.0.0.0:9000->9000/tcp, :::9000->9000/tcp, 10000/tcp   reverse_tunnel-downstream-envoy-1
  58eba3678f20   nginxdemos/hello:plain-text   "/docker-entrypoint.…"   27 seconds ago   Up 3 seconds   80/tcp                                                                                                                                       reverse_tunnel-downstream-service-1
  49145cc8a9d1   debug/envoy:latest            "/docker-entrypoint.…"   27 seconds ago   Up 3 seconds   0.0.0.0:8085->8085/tcp, :::8085->8085/tcp, 10000/tcp, 0.0.0.0:8889->8888/tcp, :::8889->8888/tcp, 0.0.0.0:9001->9000/tcp, :::9001->9000/tcp   reverse_tunnel-upstream-envoy-1

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

- **Downstream Envoy**: Has successfully connected (``connected: 1``) to the upstream cluster with no pending connections (``connecting: 0``)
- **Upstream Envoy**: Has received reverse connections from the downstream node and cluster, as indicated by the reverse connection counters

Step 6: Test reverse tunnel
***************************

Perform an HTTP request for the service behind downstream Envoy, to upstream Envoy. This request will be sent over a reverse tunnel.

.. code-block:: console

  $ curl -H "x-remote-node-id: downstream-node" -H "x-dst-cluster-uuid: downstream-cluster" http://localhost:8085/downstream_service -v

Expected response:

.. code-block:: console

  *   Trying ::1...
  * TCP_NODELAY set
  * Connected to localhost (::1) port 8085 (#0)
  > GET /downstream_service HTTP/1.1
  > Host: localhost:8085
  > User-Agent: curl/7.61.1
  > Accept: */*
  > x-remote-node-id: downstream-node
  > x-dst-cluster-uuid: downstream-cluster
  > 
  < HTTP/1.1 200 OK
  < server: envoy
  < date: Thu, 25 Sep 2025 21:25:38 GMT
  < content-type: text/plain
  < content-length: 159
  < expires: Thu, 25 Sep 2025 21:25:37 GMT
  < cache-control: no-cache
  < x-envoy-upstream-service-time: 13
  < 
  Server address: 172.27.0.3:80
  Server name: b490f264caf9
  Date: 25/Sep/2025:21:25:38 +0000
  URI: /downstream_service
  Request ID: 41807e3cd1f6a0b601597b80f7e51513
  * Connection #0 to host localhost left intact

.. seealso::

   :ref:`Reverse Tunnels architecture overview <config_reverse_connection>`
      Learn more about Envoy's reverse tunnel functionality.
