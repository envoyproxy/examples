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

Step 3: Test per-route configuration
*************************************

The filter also supports per-route configuration overrides. The example includes a route with prefix ``/override`` that overrides the filter's header configuration.

Test the per-route override:

.. code-block:: console

   $ curl -s http://localhost:10000/override | grep x-overridden-header
   "x-overridden-header": "overridden-value"

This demonstrates that different routes can have different filter behavior without requiring separate filter instances.

Step 4: Test upstream filter
*****************************

The filter also supports upstream filter chains, where it runs on requests sent from Envoy to the backend service. The example configures the filter in the cluster's ``typed_extension_protocol_options`` to add an ``x-upstream-header: upstream-value`` header to upstream requests.

Test the upstream filter:

.. code-block:: console

   $ curl -s http://localhost:10000/ | grep x-upstream-header
   "x-upstream-header": "upstream-value"

The backend will receive both the downstream filter header (``x-custom-header``) and the upstream filter header (``x-upstream-header``).

**Use cases for upstream filters:**

- **Request transformation**: Modify requests before sending to backends
- **Authentication**: Add authentication headers for upstream services
- **Metrics**: Collect per-upstream service metrics
- **Testing**: Inject headers for canary testing or tracing

Step 5: How it works
********************

The filter implementation follows Envoy best practices with a modular structure:

**api/http_filter.proto**
   Defines the filter's configuration protobuf with two required fields:

   - ``key``: The header name to add
   - ``val``: The header value to add

   Also defines ``DecoderPerRoute`` for per-route configuration overrides.

**common/config.h / config.cc**
   Holds the parsed configuration in the ``FilterConfig`` class, using the ``Envoy::Extensions::HttpFilters::Sample`` namespace.
   
   The ``PerRouteFilterConfig`` class extends ``Router::RouteSpecificFilterConfig`` and stores per-route overrides for the header key and value.

**filter/filter.h / filter.cc**
   Implements the core filter logic by extending ``PassThroughDecoderFilter`` and overriding ``decodeHeaders()`` to inject the custom header.
   
   The filter uses ``Http::Utility::resolveMostSpecificPerFilterConfig()`` to check for per-route configuration overrides before adding headers.

**factory/factory.cc**
   Registers the filter factory with Envoy for both downstream and upstream filter chains.
   
   Uses ``DualFactoryBase`` as the base class, which provides common functionality for filters that can run in both contexts.
   
   To support both downstream and upstream registration, the factory uses a type alias pattern to avoid symbol redefinition errors:
   
   .. code-block:: cpp
   
      // Type alias is required to avoid redefinition error
      using UpstreamFilterFactory = FilterFactory;
      
      REGISTER_FACTORY(FilterFactory, Server::Configuration::NamedHttpFilterConfigFactory);
      REGISTER_FACTORY(UpstreamFilterFactory, Server::Configuration::UpstreamHttpFilterConfigFactory);
   
   This dual registration allows the filter to be referenced as ``sample`` in both downstream HTTP filter chains (in the HTTP connection manager) and upstream filter chains (in cluster ``typed_extension_protocol_options``).
   
   The factory also implements ``createRouteSpecificFilterConfigTyped()`` to parse per-route configuration and create ``PerRouteFilterConfig`` instances.

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

Per-route configuration overrides are defined within route definitions:

.. code-block:: yaml

   routes:
   - match:
       prefix: "/override"
     route:
       cluster: service_backend
     typed_per_filter_config:
       sample:
         "@type": type.googleapis.com/sample.DecoderPerRoute
         key: "x-overridden-header"
         val: "overridden-value"

The upstream filter is configured in the cluster's ``typed_extension_protocol_options``:

.. code-block:: yaml

   clusters:
   - name: service_backend
     # ... other config ...
     typed_extension_protocol_options:
       envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
         "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
         explicit_http_config:
           http_protocol_options: {}
         http_filters:
         - name: sample
           typed_config:
             "@type": type.googleapis.com/sample.Decoder
             key: "x-upstream-header"
             val: "upstream-value"
         - name: envoy.filters.http.upstream_codec
           typed_config:
             "@type": type.googleapis.com/envoy.extensions.filters.http.upstream_codec.v3.UpstreamCodec

Step 6: Modify the filter
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

   :ref:`Upstream HTTP filters <arch_overview_http_filters_upstream>`
      Learn about upstream HTTP filters and their use cases.

   `Envoy bzlmod support <https://github.com/envoyproxy/envoy/pull/42890>`_
      The Envoy PR that adds bzlmod support.

   `Bazel bzlmod <https://bazel.build/external/migration>`_
      Documentation on Bazel's new module system.
