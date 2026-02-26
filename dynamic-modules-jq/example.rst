.. _install_sandboxes_dynamic_modules_jq:

Dynamic modules jq filter
==========================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

   :ref:`jq <start_sandboxes_setup_jq>`
        Used to parse and pretty-print JSON responses.

`Dynamic modules <https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/advanced/dynamic_modules>`_
let you extend Envoy by loading native shared libraries (``.so`` files) at runtime without recompiling
Envoy itself. This example ships a Rust module that embeds the
`jaq <https://github.com/01mf02/jaq>`_ engine — a pure-Rust implementation of the
`jq <https://jqlang.github.io/jq/>`_ JSON query language — to transform HTTP request and response
bodies inline, inside the Envoy filter chain.

Two independent ``jq`` programs are compiled once at filter-configuration time and then applied to
every matching HTTP body:

``request_program``
   Transforms the **request body** before it is forwarded to the upstream service. In this example it
   removes ``password`` and ``secret`` fields so they never reach the backend.

``response_program``
   Transforms the **response body** before it is returned to the client. In this example it removes
   the ``hostname`` field that the upstream echo service exposes, keeping backend topology private.

Step 1: Build the sandbox
*************************

Change to the ``dynamic-modules-jq`` directory. The first ``docker compose up`` compiles the Rust
module inside a builder container and then bakes the resulting ``.so`` file into the Envoy image.

.. code-block:: console

   $ pwd
   examples/dynamic-modules-jq
   $ docker compose pull
   $ docker compose up --build -d
   $ docker compose ps

   NAME                                    SERVICE            STATUS    PORTS
   dynamic-modules-jq-envoy-1             envoy              running   0.0.0.0:10000->10000/tcp
   dynamic-modules-jq-upstream_service-1  upstream_service   running   8080/tcp

.. note::

   The first build downloads the Envoy SDK from GitHub and compiles Rust crates, which can take
   several minutes. Subsequent builds reuse the Docker layer cache and are much faster.

Step 2: Send a request through the proxy
*****************************************

The upstream service is a simple HTTP echo server. Without any transformation you would expect the
full request body to be visible in the upstream response.

Send a ``GET`` request to verify the proxy is running:

.. code-block:: console

   $ curl -s http://localhost:10000 | jq .
   {
     "method": "GET",
     "scheme": "http",
     "path": "/",
     "headers": { ... },
     "query_params": {},
     "body": ""
   }

Notice that the ``hostname`` field is absent — it has been removed by the response ``jq`` program
(``del(.hostname)``) before the response reached your terminal.

Step 3: See the request body transform in action
*************************************************

Send a JSON body that contains a ``password`` field:

.. code-block:: console

   $ curl -s http://localhost:10000 \
       -X POST \
       -H "Content-Type: application/json" \
       -d '{"user": "alice", "password": "s3cr3t", "action": "login"}' \
       | jq .body | jq -r .
   {"user":"alice","action":"login"}

The upstream echo server shows only ``user`` and ``action`` in the body it received — ``password``
was stripped by the request ``jq`` program (``del(.password, .secret)``) before the request left
Envoy.

.. code-block:: console

   $ curl -s http://localhost:10000 \
       -X POST \
       -H "Content-Type: application/json" \
       -d '{"user": "alice", "password": "s3cr3t", "action": "login"}' \
       | jq '.body | test("password")'
   false

Step 4: See the response body transform in action
**************************************************

The upstream service always includes a ``hostname`` field in its response that identifies the backend
container. The response ``jq`` program removes it before the client sees the response.

Verify the field has been removed from the client-facing response:

.. code-block:: console

   $ curl -s http://localhost:10000 | jq 'has("hostname")'
   false

You can also confirm the other standard echo fields are still present:

.. code-block:: console

   $ curl -s http://localhost:10000 | jq '{method, path}'
   {
     "method": "GET",
     "path": "/"
   }

Step 5: Update the jq programs
*******************************

The ``jq`` programs are part of the Envoy configuration in ``envoy.yaml``. To change them, edit
the ``filter_config`` value and rebuild the Envoy container.

The relevant section of ``envoy.yaml`` looks like this:

.. code-block:: yaml

   filter_config:
     "@type": "type.googleapis.com/google.protobuf.StringValue"
     value: |
       {
         "request_program": "del(.password, .secret)",
         "response_program": "del(.hostname)"
       }

For example, change the ``request_program`` to also remove an ``api_key`` field:

.. code-block:: yaml

   filter_config:
     "@type": "type.googleapis.com/google.protobuf.StringValue"
     value: |
       {
         "request_program": "del(.password, .secret, .api_key)",
         "response_program": "del(.hostname)"
       }

Then rebuild and restart the Envoy container:

.. code-block:: console

   $ docker compose up --build -d envoy

Verify the new field is stripped:

.. code-block:: console

   $ curl -s http://localhost:10000 \
       -X POST \
       -H "Content-Type: application/json" \
       -d '{"user": "alice", "api_key": "sk-1234", "action": "query"}' \
       | jq .body | jq -r .
   {"user":"alice","action":"query"}

.. seealso::

   :ref:`Envoy dynamic modules <arch_overview_dynamic_modules>`
      Architecture overview of the dynamic modules extension point.

   `envoyproxy/dynamic-modules-examples <https://github.com/envoyproxy/dynamic-modules-examples>`_
      A companion repository with more dynamic module examples in both Rust and Go.

   `jaq <https://github.com/01mf02/jaq>`_
      The pure-Rust ``jq`` library used by this filter.

   `jq manual <https://jqlang.github.io/jq/manual/>`_
      Reference for the ``jq`` filter language.
