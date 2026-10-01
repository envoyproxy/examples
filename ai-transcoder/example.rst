.. _install_sandboxes_ai_transcoder:

Model selection and transcoding
===============================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

   :ref:`jq <start_sandboxes_setup_jq>`
        Parse JSON output from the proxy.

   API keys
        For each provider you want to try: `OpenAI <https://platform.openai.com/api-keys>`_,
        `Anthropic <https://console.anthropic.com/settings/keys>`_ and
        `Vertex AI <https://cloud.google.com/vertex-ai/generative-ai/docs/start/api-keys>`_.

This sandbox runs Envoy as an AI gateway: clients speak one API, OpenAI Chat Completions, to one endpoint,
and Envoy sends each request to OpenAI, Anthropic or Gemini on Vertex AI in that provider's own API.

.. image:: /start/sandboxes/_include/ai-transcoder/_static/ai-transcoder.svg
   :alt: Envoy routes OpenAI requests on their model to OpenAI, Anthropic or Vertex AI, transcoding each request and response

For each request, Envoy:

- reads the request's ``model`` with the :ref:`AI Protocol Manager <config_http_filters_ai_protocol_manager>`,
  whose request info AI filter stores it as the ``envoy.ai.model.request``
  :ref:`filter state object <well_known_filter_state>`, and picks a route on it: ``gpt-*`` models go to OpenAI,
  ``claude-*`` models to Anthropic, and ``gemini-*`` models to Vertex AI. Any other model is answered by Envoy with
  a ``404``.
- converts the request into the provider's API, and the provider's response (a JSON body or a stream of
  server-sent events) back into OpenAI's, with the AI Protocol Manager's transcoder AI filter.
- sends it through a single :ref:`dynamic forward proxy <arch_overview_http_dynamic_forward_proxy>` cluster to the
  provider's host, which the route names, adding the provider's API key on the way.

.. warning::

   The AI Protocol Manager and its transcoder are alpha, and their APIs are a work in progress: Envoy logs warnings
   about them at startup.

Step 1: Set your API keys
*************************

Change to the ``ai-transcoder`` directory, and export the API key of each provider you want to use.

.. code-block:: console

   $ pwd
   examples/ai-transcoder
   $ export OPENAI_API_KEY=sk-...
   $ export ANTHROPIC_API_KEY=sk-ant-...
   $ export VERTEX_API_KEY=...

For Vertex AI, also export the Google Cloud project the key belongs to, and the location to call, ``global`` by
default:

.. code-block:: console

   $ export VERTEX_PROJECT=my-project
   $ export VERTEX_LOCATION=global

The keys are passed to the Envoy container as environment variables, and Envoy adds them to the requests it sends to
each provider: clients do not need them. A provider whose key is not set answers with its own authentication error.

Step 2: Start the sandbox
*************************

Build and start the proxy.

.. code-block:: console

   $ docker compose pull
   $ docker compose up --build -d
   $ docker compose ps

   NAME                    IMAGE                 COMMAND                  SERVICE   CREATED          STATUS                    PORTS
   ai-transcoder-proxy-1   ai-transcoder-proxy   "/docker-entrypoint.…"   proxy     10 seconds ago   Up 9 seconds (healthy)    0.0.0.0:9901->9901/tcp, 0.0.0.0:10000->10000/tcp

Envoy listens for AI requests on port ``10000``, and serves its admin interface on port ``9901``.

Alternatively, :download:`run-sandbox.sh <_include/ai-transcoder/run-sandbox.sh>` does steps 1 and 2: it asks for each
key, without echoing it, and for the Vertex AI project, then builds and starts the sandbox and follows Envoy's log,
which shows where each request went:

.. code-block:: console

   $ ./run-sandbox.sh

.. tip::

   If either port is taken on your machine, set ``PORT_PROXY`` or ``PORT_ADMIN`` before starting the sandbox, and use
   those ports in the steps below.

Step 3: Send the same request to each provider
**********************************************

Send an OpenAI chat completion request to Envoy, asking for a Claude model:

.. code-block:: console

   $ curl -s http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "In one short sentence, what is Envoy proxy?"}]}' \
       | jq
   {
     "choices": [
       {
         "finish_reason": "stop",
         "index": 0,
         "message": {
           "content": "Envoy is an open-source, high-performance proxy for cloud-native applications.",
           "role": "assistant"
         }
       }
     ],
     "created": 1790803216,
     "id": "msg_01XWk8n3jWP3kDmrzHfQyM4B",
     "model": "claude-haiku-4-5-20251001",
     "object": "chat.completion",
     "usage": {
       "completion_tokens": 19,
       "prompt_tokens": 18,
       "total_tokens": 37
     }
   }

Anthropic answered, but the reply is an OpenAI ``chat.completion``: Envoy sent the request to Anthropic's Messages API
and converted the answer, including the stop reason and the token usage.

Only the ``model`` changes between providers:

.. code-block:: console

   $ for model in gpt-4o-mini claude-haiku-4-5 gemini-2.5-flash; do
       curl -s http://localhost:10000/v1/chat/completions \
         -H 'content-type: application/json' \
         -d "{\"model\": \"${model}\", \"messages\": [{\"role\": \"user\", \"content\": \"In one short sentence, what is Envoy proxy?\"}]}" \
         | jq -r '"\(.model): \(.choices[0].message.content)"'
     done
   gpt-4o-mini-2024-07-18: Envoy is an open-source edge and service proxy designed for cloud-native applications.
   claude-haiku-4-5-20251001: Envoy is an open-source, high-performance proxy for cloud-native applications.
   gemini-2.5-flash: Envoy is an open-source, high-performance edge and service proxy designed for cloud-native applications.

Step 4: Stream a response
*************************

Ask for a stream from Gemini:

.. code-block:: console

   $ curl -sN http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "gemini-2.5-flash", "stream": true, "messages": [{"role": "user", "content": "Count from 1 to 5."}]}'
   data: {"choices":[{"delta":{"content":"1, 2, 3","role":"assistant"},"finish_reason":null,"index":0}],"created":1790803221,"id":"FXzcaMjLO5Te4_UPl9jNkQ8","model":"gemini-2.5-flash","object":"chat.completion.chunk","usage":{"prompt_tokens":8,"total_tokens":8}}

   data: {"choices":[{"delta":{"content":", 4, 5","role":"assistant"},"finish_reason":"stop","index":0}],"created":1790803221,"id":"FXzcaMjLO5Te4_UPl9jNkQ8","model":"gemini-2.5-flash","object":"chat.completion.chunk","usage":{"completion_tokens":13,"prompt_tokens":8,"total_tokens":21}}

   data: [DONE]

Envoy sent this request to Gemini's ``streamGenerateContent`` method rather than ``generateContent``, and converted
each event of Gemini's stream into an OpenAI ``chat.completion.chunk``.

Gemini's streams just end, so Envoy also added the ``data: [DONE]`` event that OpenAI clients wait for.
Anthropic's named events, from ``message_start`` to ``message_stop``, are converted the same way.

Step 5: See where each request went
***********************************

Envoy's access log shows each request's model, and the provider host and path it was sent to:

.. code-block:: console

   $ docker compose logs proxy | grep -- ' -> '
   proxy-1  | claude-haiku-4-5 -> api.anthropic.com/v1/messages 200 via_upstream
   proxy-1  | gpt-4o-mini -> api.openai.com/v1/chat/completions 200 via_upstream
   proxy-1  | claude-haiku-4-5 -> api.anthropic.com/v1/messages 200 via_upstream
   proxy-1  | gemini-2.5-flash -> aiplatform.googleapis.com/v1/projects/my-project/locations/global/publishers/google/models/gemini-2.5-flash:generateContent 200 via_upstream
   proxy-1  | gemini-2.5-flash -> aiplatform.googleapis.com/v1/projects/my-project/locations/global/publishers/google/models/gemini-2.5-flash:streamGenerateContent?alt=sse 200 via_upstream

The log reads the model from the ``envoy.ai.model.request`` filter state object, with
``%FILTER_STATE(envoy.ai.model.request:PLAIN)%``.

Every client sent its request to ``/v1/chat/completions``. The Gemini requests show the model moved from the request
body into the Vertex AI path, and the streaming one calling ``streamGenerateContent``.

Step 6: Ask for a model that no provider serves
***********************************************

A model that no route matches never leaves Envoy. It is answered with a ``404``, in OpenAI's error format so that
OpenAI clients can read it:

.. code-block:: console

   $ curl -si http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "llama-3.1-8b", "messages": [{"role": "user", "content": "Hi"}]}'
   HTTP/1.1 404 Not Found
   content-type: application/json
   content-length: 133
   date: Wed, 30 Sep 2026 21:36:05 GMT
   server: envoy

   {"error": {"message": "No backend serves this model.", "type": "invalid_request_error", "param": "model", "code": "model_not_found"}}

Step 7: Check the transcoder's statistics
*****************************************

The AI Protocol Manager counts the request bodies it parsed, the models it read, and the payloads it transcoded
(each request, JSON response and streamed event), and the ones it could not:

.. code-block:: console

   $ curl -s "http://localhost:9901/stats?filter=ai_protocol_manager.(request_parsed|request_info.published|transcoder)"
   ai_protocol_manager.request_info.published: 6
   ai_protocol_manager.request_parsed: 11
   ai_protocol_manager.transcoder.failed: 0
   ai_protocol_manager.transcoder.transcoded: 22
   ai_protocol_manager.transcoder.unresolved: 0

The sandbox runs two AI Protocol Managers, which count together: one read the model of all six requests, and the
other parsed the five that a provider served, to transcode them.

Step 8: Use an OpenAI SDK
*************************

Any OpenAI client library can use the sandbox, by pointing its base URL at Envoy. For example, with the
`OpenAI Python library <https://pypi.org/project/openai/>`_:

.. code-block:: python

   from openai import OpenAI

   # Envoy adds each provider's key, so the client's is not used.
   client = OpenAI(base_url="http://localhost:10000/v1", api_key="unused")

   for model in ["gpt-4o-mini", "claude-haiku-4-5", "gemini-2.5-flash"]:
       stream = client.chat.completions.create(
           model=model,
           messages=[{"role": "user", "content": "Write a haiku about proxies."}],
           stream=True,
       )
       print(f"{model}:")
       for chunk in stream:
           if chunk.choices:
               print(chunk.choices[0].delta.content or "", end="", flush=True)
       print("\n")

How the configuration works
***************************

Routing on the model
~~~~~~~~~~~~~~~~~~~~

The model is in the request body, but Envoy picks a route as soon as the request headers arrive, before the body is
read. So every chat request starts on the last route, ``unknown_model``. It declares the request's API for the first
AI Protocol Manager, ``read_model``, which therefore parses the body:

.. literalinclude:: _include/ai-transcoder/envoy.yaml
   :language: yaml
   :lines: 109-126
   :lineno-start: 109
   :linenos:
   :emphasize-lines: 15-18

``read_model`` runs the request info AI filter, which stores the model as the ``envoy.ai.model.request`` filter state
object. As that filter only reads the request, ``read_model`` forwards the body as it was received. The
``set_filter_state`` filter then clears the route cache, so that the route is picked again, now that the model is
known:

.. literalinclude:: _include/ai-transcoder/envoy.yaml
   :language: yaml
   :lines: 127-143
   :lineno-start: 127
   :linenos:

Each provider has a route that matches its models. Here is Anthropic's, in the
:download:`envoy.yaml <_include/ai-transcoder/envoy.yaml>` configuration:

.. literalinclude:: _include/ai-transcoder/envoy.yaml
   :language: yaml
   :lines: 56-81
   :lineno-start: 56
   :linenos:
   :emphasize-lines: 4-6, 19-23

The route:

- matches a model starting with ``claude-``, with a :ref:`filter state <envoy_v3_api_field_config.route.v3.RouteMatch.filter_state>`
  matcher on ``envoy.ai.model.request``.
- declares the APIs to transcode between, with the AI Protocol Manager's
  :ref:`per-route configuration <envoy_v3_api_msg_extensions.filters.http.ai_protocol_manager.v3.AiProtocolManagerPerRoute>`
  for the second AI Protocol Manager, ``transcode``: the client's request API is OpenAI Chat Completions, and the
  provider's API is Anthropic Messages.
- names the provider's host for the dynamic forward proxy, with ``host_rewrite_literal``.
- rewrites the path to Anthropic's, removes the client's ``authorization`` header, and adds Anthropic's key header,
  whose value Envoy reads from the ``ANTHROPIC_API_KEY`` environment variable.

The routes only differ in these settings:

.. list-table::
   :header-rows: 1

   * - Model
     - Provider API
     - Host
     - Path
     - API key header
   * - ``gpt-*``
     - OpenAI Chat Completions
     - ``api.openai.com``
     - ``/v1/chat/completions``
     - ``authorization: Bearer $OPENAI_API_KEY``
   * - ``claude-*``
     - Anthropic Messages
     - ``api.anthropic.com``
     - ``/v1/messages``
     - ``x-api-key: $ANTHROPIC_API_KEY``, and ``anthropic-version``
   * - ``gemini-*``
     - Gemini GenerateContent
     - ``aiplatform.googleapis.com``
     - ``/v1/projects/$VERTEX_PROJECT/locations/$VERTEX_LOCATION/publishers/google/models/{model}:generateContent``,
       or ``:streamGenerateContent?alt=sse``
     - ``x-goog-api-key: $VERTEX_API_KEY``

A request whose model no route serves stays on ``unknown_model``, and gets its ``404``.

Transcoding
~~~~~~~~~~~

An AI Protocol Manager reads the APIs a route declares when the request headers reach it. ``read_model`` sees them
before the route is picked on the model, so the transcoding is done by a second AI Protocol Manager, ``transcode``,
placed after ``set_filter_state``: it sees the model's route. It holds the request until its body is parsed, then
runs its AI filters over it:

.. literalinclude:: _include/ai-transcoder/envoy.yaml
   :language: yaml
   :lines: 144-160
   :lineno-start: 144
   :linenos:

Every API is translated through one canonical form, OpenAI Chat Completions. The first transcoder converts the
client's request into it, from the route's request API, and the second converts it into the route's response API,
the provider's. Responses take the reverse path, one JSON body or one streamed event at a time.

As the client already speaks OpenAI Chat Completions, the first transcoder leaves its requests as they are. It is where
a client of another API would be converted, on a route declaring that API as its request API.

Gemini carries the model, and whether to stream, in the request path rather than the body. The transcoder moves both
into the Gemini API's path, ``/v1beta/models/{model}:generateContent`` or ``:streamGenerateContent?alt=sse``, which the
Vertex AI route then maps onto Vertex AI's:

.. literalinclude:: _include/ai-transcoder/envoy.yaml
   :language: yaml
   :lines: 88-96
   :lineno-start: 88
   :linenos:

A route's path rewrite cannot read the environment, so the proxy fills in ``VERTEX_PROJECT`` and ``VERTEX_LOCATION``
as it starts, from the :download:`docker-compose.yaml <_include/ai-transcoder/docker-compose.yaml>` composition:

.. literalinclude:: _include/ai-transcoder/docker-compose.yaml
   :language: yaml
   :lines: 10-18
   :lineno-start: 10
   :linenos:

.. note::

   A Vertex AI express mode API key belongs to no project. To use one, change the substitution to
   ``/v1/publishers/google/models/\1``.

The AI Protocol Manager cannot read a compressed response, so the routes remove the client's ``accept-encoding``
header.

One cluster for every provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``dynamic_forward_proxy`` HTTP filter looks up the host that the route names, and the requests of every route go
to the same :ref:`dynamic forward proxy <arch_overview_http_dynamic_forward_proxy>` cluster, which connects to it:

.. literalinclude:: _include/ai-transcoder/envoy.yaml
   :language: yaml
   :lines: 171-189
   :lineno-start: 171
   :linenos:

The cluster uses TLS, with the host as the SNI and as the name the provider's certificate is validated against. Adding
a provider takes a route, not a cluster.

Limitations
~~~~~~~~~~~

- An error response, such as the ``401`` of a provider whose key is not set, is forwarded in the provider's own
  format: the transcoder only converts successful responses.
- Not every field has a mapping yet: tool calls are not transcoded for Anthropic and Gemini.
- Each request is parsed twice, once by each AI Protocol Manager.

.. seealso::

   :ref:`AI Protocol Manager <config_http_filters_ai_protocol_manager>`
      Learn more about the AI Protocol Manager filter and its AI filters.

   :ref:`Transcoder API <envoy_v3_api_msg_extensions.http.ai_filters.transcoder.v3.Transcoder>`
      The transcoder AI filter's configuration.

   :ref:`Well known filter state <well_known_filter_state>`
      Learn more about the ``envoy.ai.model.request`` filter state object.

   :ref:`Set filter state <config_http_filters_set_filter_state>`
      Learn more about the set filter state filter.

   :ref:`Dynamic forward proxy <arch_overview_http_dynamic_forward_proxy>`
      Learn more about Envoy's dynamic forward proxy.
