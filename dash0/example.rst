.. _install_sandboxes_dash0:

Dash0 tracing
=============

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.


.. note::

   Before proceeding, please ensure you have a Dash0 account set up.

   If you don't already have one, you can `sign up for Dash0 here <https://www.dash0.com/sign-up>`_.


The Dash0 tracing sandbox demonstrates Envoy's :ref:`request tracing <arch_overview_tracing>`
capabilities using `Dash0 <https://www.dash0.com/>`_ as the tracing backend.

In this example, a backend service is provided:

- ``service-1``

An `OpenTelemetry Collector <https://opentelemetry.io/docs/collector/>`_ is also provided, which
receives spans from Envoy and forwards them to your Dash0 organization over OTLP.

The ``envoy`` service is exposed on port ``10000`` and the request flow is as follows:

    User -> ``envoy`` -> ``service-1``

The Envoy proxy is configured (:download:`envoy.yaml <_include/dash0/envoy.yaml>`) to generate a
span for each request and export it, over gRPC, to a cluster named ``dash0_collector`` pointing at
the local collector. The collector (:download:`otel-collector-config.yaml
<_include/dash0/otel-collector-config.yaml>`) in turn exports those spans to Dash0's OTLP ingress
endpoint, with your auth token and target dataset carried in the ``Authorization`` and
``Dash0-Dataset`` headers.

Each span records the latency of the upstream call as well as information needed to correlate
the span with other related spans (e.g., the trace ID).

Step 1: Get a Dash0 auth token and OTLP endpoint
*************************************************

From your Dash0 organization settings, create an auth token and note the OTLP gRPC ingress
endpoint for your organization's region (for example ``ingress.eu-west-1.aws.dash0.com:4317``).

Step 2: Build the sandbox
**************************

Change to the ``dash0`` directory, and start the containers, with the following commands:

.. code-block:: console

    $ pwd
    examples/dash0
    $ export DASH0_AUTH_TOKEN=<YOUR_AUTH_TOKEN>
    $ export DASH0_DATASET=<YOUR_DATASET>
    $ export DASH0_ENDPOINT=<YOUR_OTLP_GRPC_ENDPOINT>
    $ docker compose pull
    $ docker compose up --build -d
    $ docker compose ps

                Name                          Command                State                  Ports
    -----------------------------------------------------------------------------------------------------------
    dash0-dash0-collector-1      "/otelcol --config=…"           running (healthy)
    dash0-envoy-1                "/docker-entrypoint.…"           running      0.0.0.0:10000->10000/tcp
    dash0-service-1-1            "python3 /code/servi…"           running (healthy)

Step 3: Make a request to ``service-1``
****************************************

Now send a request to ``service-1``, by calling http://localhost:10000/trace/1.

.. code-block:: console

    $ curl localhost:10000/trace/1
    Hello from behind Envoy (service 1)!

Step 4: View the trace in Dash0
*********************************

Log in to your Dash0 organization and navigate to the Traces view.

You should see a trace for the ``envoy-dash0-demo`` service, named after the
``tracing.provider.typed_config.service_name`` value set in ``envoy.yaml``.

.. image:: /start/sandboxes/_include/dash0/_static/dash0-ui-traces.png

Click into it to see the span recorded for the proxied request, including its latency and
metadata such as ``http.response.status_code`` and ``component``.

.. image:: /start/sandboxes/_include/dash0/_static/dash0-ui-trace.png

.. seealso::

   :ref:`Request tracing <arch_overview_tracing>`
      Learn more about using Envoy's request tracing.

   `Dash0 <https://www.dash0.com/>`_
      Dash0 website.

   `OpenTelemetry tracing <https://opentelemetry.io/>`_
      OpenTelemetry tracing sandbox.
