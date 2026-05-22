.. _install_sandboxes_http_filter_cc:

HTTP filter (C++)
=================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

   :ref:`jq <start_sandboxes_setup_jq>`
        Used to parse JSON output.

This example demonstrates how to build a custom Envoy HTTP filter.

The example creates simple upstream and downstream HTTP decoder filters that add custom headers to
incoming requests.

The filter is statically linked into a custom Envoy binary built from source.

.. note::

   Building the custom Envoy binary will take significant time and disk space (20GB) on the first run.

Bazel module configuration
--------------------------

The filter declares Envoy as a bzlmod dependency, using overrides to point to a specific repository commit:

.. literalinclude:: _include/http-filter-cc/MODULE.bazel
   :language: starlark
   :linenos:
   :lines: 1-35
   :emphasize-lines: 7-8, 22-26
   :caption: :download:`MODULE.bazel <_include/http-filter-cc/MODULE.bazel>`

Protobuf configuration
----------------------

The filter's configuration is defined in a protobuf with two required fields for the header key and value, and a per-route configuration message:

.. literalinclude:: _include/http-filter-cc/api/http_filter.proto
   :language: proto
   :linenos:
   :caption: :download:`http_filter.proto <_include/http-filter-cc/api/http_filter.proto>`

FilterConfig class
------------------

The parsed configuration is held in the ``FilterConfig`` class, using the ``Envoy::Extensions::HttpFilters::Sample`` namespace.

The ``PerRouteFilterConfig`` class extends ``Router::RouteSpecificFilterConfig`` and stores per-route overrides:

.. literalinclude:: _include/http-filter-cc/common/config.h
   :language: cpp
   :linenos:
   :lines: 1-53
   :emphasize-lines: 18-28, 35-46
   :caption: :download:`config.h <_include/http-filter-cc/common/config.h>`

Filter implementation
---------------------

The core filter logic extends ``PassThroughDecoderFilter`` and overrides ``decodeHeaders()`` to inject the custom header.

The filter uses ``Http::Utility::resolveMostSpecificPerFilterConfig()`` to check for per-route configuration overrides:

.. literalinclude:: _include/http-filter-cc/filter/filter.cc
   :language: cpp
   :linenos:
   :lines: 19-37
   :lineno-start: 19
   :emphasize-lines: 5-7, 9-16
   :caption: :download:`filter.cc <_include/http-filter-cc/filter/filter.cc>`

Factory registration
--------------------

The filter factory uses ``DualFactoryBase`` as the base class, providing common functionality for filters that can run in both downstream and upstream contexts.

To support both downstream and upstream registration, the factory uses a type alias pattern:

.. literalinclude:: _include/http-filter-cc/factory/factory.cc
   :language: cpp
   :linenos:
   :lines: 1-52
   :emphasize-lines: 19, 24-32, 34-38, 43-47
   :caption: :download:`factory.cc <_include/http-filter-cc/factory/factory.cc>`

This dual registration allows the filter to be referenced as ``sample`` in both downstream HTTP filter chains and upstream filter chains.

Step 1: Start the containers
*****************************

The example consists of two services:

- **envoy**: A custom Envoy binary with the HTTP filter statically linked
- **echo**: An echo service that responds to HTTP requests

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
    http-filter-cc_envoy_1     /usr/local/bin/envoy -c ...   Up      0.0.0.0:10000->10000/tcp
    http-filter-cc_echo_1   example-echo -c /etc/con...   Up      8080/tcp

Step 2: Test the downstream filter
**********************************

The downstream filter adds a header ``x-downstream-header: downstream-value`` to all requests it receives
from downstream. The included header is forwarded to routed upstreams.

The downstream filter is configured in the HTTP connection manager filter chain:

.. literalinclude:: _include/http-filter-cc/envoy.yaml
   :language: yaml
   :linenos:
   :lines: 14-22
   :lineno-start: 14
   :emphasize-lines: 1-6
   :caption: :download:`envoy.yaml <_include/http-filter-cc/envoy.yaml>`

Make a request to the Envoy proxy and verify the custom header is added:

.. code-block:: console

   $ curl -s http://localhost:10000/ | jq '.headers["x-downstream-header"]'
   "downstream-value"

Step 3: Test per-route configuration
*************************************

The filter supports per-route configuration overrides. The example includes a route with prefix ``/override`` that overrides the
filter's header configuration.

Per-route configuration overrides are defined within route definitions using ``typed_per_filter_config``:

.. literalinclude:: _include/http-filter-cc/envoy.yaml
   :language: yaml
   :linenos:
   :lines: 28-38
   :lineno-start: 28
   :emphasize-lines: 5-10
   :caption: :download:`envoy.yaml <_include/http-filter-cc/envoy.yaml>`

Test the per-route override:

.. code-block:: console

   $ curl -s http://localhost:10000/override | jq '.headers["x-overridden-header"]'
   "overridden-value"

This demonstrates that different routes can have different filter behavior without requiring separate filter instances.

Step 4: Test the upstream filter
********************************

The filter also supports upstream filter chains, where it runs on requests sent from Envoy to the echo service.

The example configures the filter in the cluster's ``typed_extension_protocol_options`` to add an ``x-upstream-header: upstream-value``
header to upstream requests.

Test the upstream filter:

.. code-block:: console

   $ curl -s http://localhost:10000/ | jq '.headers["x-upstream-header"]'
   "upstream-value"

The echo service will receive both the downstream filter header (``x-downstream-header``) and the upstream filter header (``x-upstream-header``):

.. code-block:: console

   $ curl -s http://localhost:10000/ | jq '.headers | with_entries(select(.key | startswith("x-")))'
   {
     "x-downstream-header": "downstream-value",
     "x-upstream-header": "upstream-value"
   }

Step 5: Modify the filter configuration
****************************************

You can modify the filter configuration in ``envoy.yaml`` to change the header name and value.

For example, edit the configuration to add a different header:

.. code-block:: yaml

   - name: sample
     typed_config:
       "@type": type.googleapis.com/sample.Decoder
       key: "x-my-header"
       val: "my-value"

Then restart Envoy:

.. code-block:: console

   $ docker compose up -d envoy
   $ curl -s http://localhost:10000/ | jq '.headers["x-my-header"]'
   "my-value"

Step 5: Rebuild the filter
**************************

After making changes to the filter source code, you should rebuild it.

.. code-block:: console

   $ docker compose up --build -d envoy

.. seealso::

   :ref:`Envoy HTTP filters <config_http_filters>`
      Learn more about Envoy HTTP filters.

   :ref:`Upstream HTTP filters <arch_overview_http_filters_upstream>`
      Learn about upstream HTTP filters and their use cases.
