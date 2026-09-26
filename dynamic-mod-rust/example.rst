.. _install_sandboxes_dynamic_mod_rust:

Dynamic modules (Rust HTTP filter)
==================================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

This sandbox demonstrates a basic Envoy :ref:`dynamic module <arch_overview_dynamic_modules>` written in Rust
with the `Rust SDK <https://github.com/envoyproxy/envoy/tree/main/source/extensions/dynamic_modules/sdk/rust>`_.

Dynamic modules are shared libraries that Envoy loads at runtime, and are the recommended way of extending
Envoy with custom code without recompiling it.

In this example, the module is loaded by an
:ref:`HTTP filter <envoy_v3_api_msg_extensions.filters.http.dynamic_modules.v3.DynamicModuleFilter>`
which adds a header to, and appends some text to the body of, responses proxied by Envoy.

The module is built from :download:`source <_include/dynamic-mod-rust/src/lib.rs>` in the first stage of a
multi-stage Docker build, so no build tools are required on the host, and no prebuilt binaries are
shipped with the example.

.. note::

   The Rust SDK is consumed as a git dependency on the `Envoy repository <https://github.com/envoyproxy/envoy>`_,
   pinned in the example's :download:`Cargo.toml <_include/dynamic-mod-rust/Cargo.toml>`:

   .. literalinclude:: _include/dynamic-mod-rust/Cargo.toml
      :language: toml
      :lines: 8-15
      :lineno-start: 8
      :linenos:
      :emphasize-lines: 7

   The SDK version must match the ABI version of the Envoy binary that loads the module - the pinned
   revision should be kept in sync with the Envoy image used in
   :download:`Dockerfile-proxy <_include/dynamic-mod-rust/Dockerfile-proxy>`.

   Per the :ref:`ABI compatibility policy <arch_overview_dynamic_modules>`, a module built with the SDK
   for a given Envoy version keeps working with later Envoy versions, but not necessarily with earlier
   ones.

Step 1: Start all of our containers
***********************************

First lets start the containers - an Envoy proxy which loads the dynamic module, and a backend which
echos back our request.

The module is compiled in the first stage of the proxy image build, which may take a few minutes the
first time it is run.

Change to the ``dynamic-mod-rust`` directory, and start the composition:

.. code-block:: console

    $ pwd
    examples/dynamic-mod-rust
    $ docker compose pull
    $ docker compose up --build -d
    $ docker compose ps

    NAME                             COMMAND                  SERVICE       STATUS
    dynamic-mod-rust-proxy-1         "/docker-entrypoint.…"   proxy         Up
    dynamic-mod-rust-web_service-1   "/bin/echo-server"       web_service   Up

Step 2: Check web response
**************************

The module appends ``Hello from the Rust dynamic module`` to the body of every response from the
upstream service.

.. code-block:: console

   $ curl -s http://localhost:10000 | grep "Hello"
   Hello from the Rust dynamic module

It also adds an ``x-dynamic-module`` header to the response.

.. code-block:: console

   $ curl -sI http://localhost:10000 | grep "x-dynamic-module"
   x-dynamic-module: FOO

Both the header and the appended body text are set in the ``filter_config`` of the
:download:`envoy.yaml <_include/dynamic-mod-rust/envoy.yaml>` configuration, which Envoy passes to
the module as JSON:

.. literalinclude:: _include/dynamic-mod-rust/envoy.yaml
   :language: yaml
   :lines: 27-43
   :lineno-start: 27
   :linenos:
   :emphasize-lines: 12-17

Step 3: Update the filter configuration
***************************************

Stop the proxy server and change the value of the ``response_header_value`` in the ``filter_config``
of ``envoy.yaml`` from ``FOO`` to ``BAR``:

.. code-block:: console

   $ docker compose stop proxy
   $ sed -i s/FOO/BAR/ envoy.yaml

Now, rebuild and start the proxy container:

.. code-block:: console

   $ docker compose up --build --force-recreate -d proxy

As the module itself is unchanged, its build is fully cached, and only the Envoy configuration is
updated in the rebuilt image.

Step 4: Check the proxy has been updated
****************************************

The response header set by the module should have changed:

.. code-block:: console

   $ curl -sI http://localhost:10000 | grep "x-dynamic-module"
   x-dynamic-module: BAR

.. tip::

   You can also change the behavior of the module itself by editing
   :download:`src/lib.rs <_include/dynamic-mod-rust/src/lib.rs>` and rebuilding the proxy in the
   same way - in this case the module is recompiled as part of the image build.

.. seealso::

   :ref:`Dynamic modules <arch_overview_dynamic_modules>`
      Overview of Envoy's dynamic modules, including the ABI compatibility policy.

   :ref:`Dynamic module HTTP filter API <envoy_v3_api_msg_extensions.filters.http.dynamic_modules.v3.DynamicModuleFilter>`
      The API for configuring HTTP filter dynamic modules.

   `Rust SDK <https://github.com/envoyproxy/envoy/tree/main/source/extensions/dynamic_modules/sdk/rust>`_
      The Rust SDK for Envoy dynamic modules.

   `Dynamic modules examples <https://github.com/envoyproxy/dynamic-modules-examples>`_
      Further examples of Envoy dynamic modules.
