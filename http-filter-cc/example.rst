.. _install_sandboxes_http_filter_cc:

HTTP filter (C++ / bzlmod)
===========================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

This example demonstrates how to build a custom Envoy HTTP filter using bzlmod (Bazel's new module system).

The example creates a simple HTTP decoder filter that adds a custom header to incoming requests.
The filter is statically linked into a custom Envoy binary built from source.

This approach replaces the obsolete WORKSPACE-based method and shows how to use Envoy as a bzlmod dependency.

.. note::

   This example requires Bazel 7.6.2 or later and uses the Envoy bzlmod support.

Step 1: Build the custom Envoy binary
**************************************

The first step is to compile the custom Envoy binary with the HTTP filter statically linked.

This uses the ``envoy-build`` service which runs Bazel inside a build container.

.. warning::

   This step uses the
   `envoyproxy/envoy-build <https://hub.docker.com/r/envoyproxy/envoy-build/tags>`_ image.
   You will need 4-5GB of disk space and the build will take some time on the first run.

Export ``UID`` from your host system to ensure the binary has the correct permissions:

.. code-block:: console

   $ export UID
   $ cd http-filter-cc
   $ docker compose run --rm envoy-build

The compiled binary will be placed in the ``bin/`` directory:

.. code-block:: console

   $ ls -lh bin/
   total 200M
   -rwxr-xr-x 1 user user 200M Feb  3 10:00 envoy

Step 2: Start the containers
*****************************

Now start the proxy and backend services:

.. code-block:: console

    $ docker compose pull
    $ docker compose up --build -d proxy backend
    $ docker compose ps

          Name                    Command                  State           Ports
    ------------------------------------------------------------------------------------
    http-filter-cc_proxy_1     /usr/local/bin/envoy -c ...   Up      0.0.0.0:10000->10000/tcp
    http-filter-cc_backend_1   example-echo -c /etc/con...   Up      8080/tcp

Step 3: Test the custom filter
*******************************

The custom filter is configured to add a header ``x-custom-header: custom-value`` to all requests.

Make a request to the proxy and check for the custom header in the upstream request:

.. code-block:: console

   $ curl -v http://localhost:10000/

The backend echo service will show the headers it received, including the custom header added by the filter:

.. code-block:: console

   $ curl -s http://localhost:10000/ | grep x-custom-header
   "x-custom-header": "custom-value"

You can also check Envoy's admin interface to see stats and config:

.. code-block:: console

   $ docker compose exec proxy curl -s http://localhost:9001/stats | grep http
   $ docker compose exec proxy curl -s http://localhost:9001/config_dump

Step 4: How it works
********************

The filter implementation consists of several components:

**http_filter.proto**
   Defines the filter's configuration protobuf with two required fields:

   - ``key``: The header name to add
   - ``val``: The header value to add

**http_filter.h / http_filter.cc**
   Implements the filter logic by extending ``PassThroughDecoderFilter`` and overriding ``decodeHeaders()`` to inject the custom header.

**http_filter_config.cc**
   Registers the filter factory with Envoy using ``NamedHttpFilterConfigFactory``, allowing the filter to be referenced as ``sample`` in the Envoy configuration.

**MODULE.bazel**
   Declares Envoy as a bzlmod dependency:

   .. literalinclude:: _include/http-filter-cc/MODULE.bazel
      :language: starlark
      :lines: 1-10

**BUILD**
   Defines the build targets:

   .. literalinclude:: _include/http-filter-cc/BUILD
      :language: starlark
      :lines: 1-39

The filter is configured in :download:`envoy.yaml <_include/http-filter-cc/envoy.yaml>`:

.. literalinclude:: _include/http-filter-cc/envoy.yaml
   :language: yaml
   :lines: 14-19
   :emphasize-lines: 1-6

Step 5: Modify the filter
**************************

You can modify the filter configuration in ``envoy.yaml`` to change the header name and value.

For example, edit the configuration to add a different header:

.. code-block:: yaml

   - name: sample
     typed_config:
       "@type": type.googleapis.com/sample.Decoder
       key: "x-my-header"
       val: "my-value"

Then rebuild and restart the proxy:

.. code-block:: console

   $ docker compose up --build -d proxy
   $ curl -s http://localhost:10000/ | grep x-my-header
   "x-my-header": "my-value"

.. seealso::

   :ref:`Envoy HTTP filters <config_http_filters>`
      Learn more about Envoy HTTP filters.

   `Envoy bzlmod support <https://github.com/envoyproxy/envoy/pull/42890>`_
      The Envoy PR that adds bzlmod support.

   `Bazel bzlmod <https://bazel.build/external/migration>`_
      Documentation on Bazel's new module system.
