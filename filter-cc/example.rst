.. _install_sandboxes_filter_cc:

C++ HTTP filter (statically linked)
===================================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

This sandbox demonstrates how to build a native C++ HTTP filter and statically link it
into the Envoy binary using `bzlmod <https://bazel.build/external/module>`_.

The example filter is a decoder filter which reads a ``key`` and ``val`` from its
configuration, and adds them as a header to proxied requests.

The example provides all of the pieces required to build and use an Envoy extension:

:download:`MODULE.bazel <_include/filter-cc/MODULE.bazel>`
   Declares the module and its dependency on the ``envoy`` and ``envoy_api`` Bazel modules,
   and sets up the compiler toolchain. This is the file to copy when starting your own extension.

:download:`BUILD <_include/filter-cc/BUILD>`
   Builds the filter's config proto, the filter itself and an Envoy binary with the
   filter statically linked, using Envoy's build macros.

:download:`http_filter.proto <_include/filter-cc/http_filter.proto>`
   The configuration proto for the filter.

:download:`http_filter.h <_include/filter-cc/http_filter.h>` / :download:`http_filter.cc <_include/filter-cc/http_filter.cc>`
   The filter itself - an implementation of ``Envoy::Http::PassThroughDecoderFilter``
   which adds the configured header to requests.

:download:`http_filter_config.cc <_include/filter-cc/http_filter_config.cc>`
   The config factory which registers the filter with Envoy, making it available
   as the ``sample`` filter in Envoy configuration.

:download:`http_filter_integration_test.cc <_include/filter-cc/http_filter_integration_test.cc>`
   An integration test which spins up the filter inside Envoy's HTTP integration test
   framework and asserts the header is added.

:download:`envoy.yaml <_include/filter-cc/envoy.yaml>`
   An Envoy configuration using the ``sample`` filter.

Step 1: Build the Envoy binary with the filter
**********************************************

.. warning::

   These instructions for building the binary use the
   `envoyproxy/envoy-build-ubuntu <https://hub.docker.com/r/envoyproxy/envoy-build-ubuntu/tags>`_ image.
   You will need 4-5GB of disk space to accommodate this image, and building Envoy
   itself requires significant time, cpu and memory.

Export ``UID`` from your host system. This will ensure that the binary created inside the
build container has the same permissions as your host user:

.. code-block:: console

   $ export UID

Change to the ``filter-cc`` directory and build the Envoy binary with the ``sample``
filter statically linked:

.. code-block:: console

    $ pwd
    examples/filter-cc
    $ docker compose -f docker-compose-build.yaml run --remove-orphans filter_build

The built binary should now be in the ``bin`` folder.

.. code-block:: console

   $ ls -l bin
   total 803408
   -r-xr-xr-x 1 user user 822683320 Oct 20 10:16 envoy

Step 2: Start all of our containers
***********************************

Start the composition - an Envoy proxy which uses the binary built in Step 1, and a
backend which echos back our request:

.. code-block:: console

    $ pwd
    examples/filter-cc
    $ docker compose up --build -d
    $ docker compose ps

    NAME                       COMMAND                  SERVICE       STATUS    PORTS
    filter-cc-proxy-1          "/usr/local/bin/envo…"   proxy         running   0.0.0.0:8000->8000/tcp
    filter-cc-web_service-1    "/bin/echo-server"       web_service   running   8080/tcp

Step 3: Check the filter has added its header
*********************************************

The ``sample`` filter is configured in :download:`envoy.yaml <_include/filter-cc/envoy.yaml>`
to add a ``via: sample-filter`` header to proxied requests:

.. literalinclude:: _include/filter-cc/envoy.yaml
   :language: yaml
   :lines: 26-31
   :lineno-start: 26
   :emphasize-lines: 2-6
   :linenos:

As the backend service echos the request it receives, the header added by the filter
should be visible in the response body:

.. code-block:: console

   $ curl -s http://localhost:8000 | grep "sample-filter"
   Via: sample-filter

Step 4: Run the integration test
********************************

The example also provides an integration test which exercises the filter inside
Envoy's HTTP integration test framework, without the need to build - or run - the
Envoy binary:

.. code-block:: console

    $ pwd
    examples/filter-cc
    $ docker compose -f docker-compose-build.yaml run --remove-orphans filter_test

.. seealso::

   :ref:`HTTP filters <arch_overview_http_filters>`
      Further information about Envoy's HTTP filters.

   :ref:`Envoy Bazel build <install_requirements>`
      Building Envoy with Bazel.

   `Envoy filter example <https://github.com/envoyproxy/examples/tree/main/filter-cc>`_
      The source files for this example.
