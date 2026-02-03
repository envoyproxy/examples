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
   Building the custom Envoy binary will take significant time and disk space (4-5GB) on the first run.

Step 1: Start the containers
*****************************

The example consists of two services:

- **proxy**: A custom Envoy binary with the HTTP filter statically linked
- **backend**: An echo service that responds to HTTP requests

The custom Envoy binary is compiled during the Docker build process.

Change to the ``http-filter-cc`` directory and start the containers:

.. code-block:: console

    $ pwd
    examples/http-filter-cc
    $ docker compose pull
    $ docker compose up --build -d
    $ docker compose ps

          Name                    Command                  State           Ports
    ------------------------------------------------------------------------------------
    http-filter-cc_proxy_1     /usr/local/bin/envoy -c ...   Up      0.0.0.0:10000->10000/tcp
    http-filter-cc_backend_1   example-echo -c /etc/con...   Up      8080/tcp

Step 2: Test the custom filter
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

Step 3: How it works
********************

The filter implementation follows Envoy best practices with a modular structure:

**api/http_filter.proto**
   Defines the filter's configuration protobuf with two required fields:

   - ``key``: The header name to add
   - ``val``: The header value to add

   Also defines ``DecoderPerRoute`` for per-route configuration overrides.

**common/config.h / config.cc**
   Holds the parsed configuration in the ``FilterConfig`` class, using the ``Envoy::Extensions::HttpFilters::Sample`` namespace.

**filter/filter.h / filter.cc**
   Implements the core filter logic by extending ``PassThroughDecoderFilter`` and overriding ``decodeHeaders()`` to inject the custom header.

**factory/factory.cc**
   Registers the filter factory with Envoy using ``DualFactoryBase`` and the ``REGISTER_FACTORY`` macro, allowing the filter to be referenced as ``sample`` in the Envoy configuration.

**MODULE.bazel**
   Declares Envoy as a bzlmod dependency:

   .. literalinclude:: _include/http-filter-cc/MODULE.bazel
      :language: starlark
      :lines: 1-10

**BUILD.bazel**
   Defines the build targets:

   .. literalinclude:: _include/http-filter-cc/BUILD.bazel
      :language: starlark
      :lines: 1-16

The filter is configured in :download:`envoy.yaml <_include/http-filter-cc/envoy.yaml>`:

.. literalinclude:: _include/http-filter-cc/envoy.yaml
   :language: yaml
   :lines: 14-19
   :emphasize-lines: 1-6

Step 4: Modify the filter
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
