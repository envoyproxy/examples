.. _install_sandboxes_ai_transcoder:

Model selection and transcoding
===============================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

   :ref:`jq <start_sandboxes_setup_jq>`
        Parse JSON output from the proxy.

This sandbox runs Envoy as an AI gateway: clients speak one API, OpenAI Chat Completions, to one endpoint,
and Envoy sends each request to an OpenAI, Anthropic or Gemini upstream in that provider's own API.

The upstreams are local mocks that speak each provider's wire format, unary JSON and server-sent events,
with canned responses: the sandbox needs no API keys, and its output is deterministic. The point of the
example is Envoy's transcoding, which works the same against the real services.

.. image:: /start/sandboxes/_include/ai-transcoder/_static/ai-transcoder.svg
   :alt: Envoy routes OpenAI requests on their model to an OpenAI, Anthropic or Gemini upstream, transcoding each request and response

For each request, Envoy:

- reads the request's ``model`` with the :ref:`AI Protocol Manager <config_http_filters_ai_protocol_manager>`,
  whose request info AI filter stores it as the ``envoy.ai.model.request``
  :ref:`filter state object <well_known_filter_state>`, and picks a route on it: ``gpt-*`` models go to the
  OpenAI upstream, ``claude-*`` models to Anthropic, and ``gemini-*`` models to Gemini. Any other model is
  answered by Envoy with a ``404``.
- converts the request into the provider's API, and the provider's response (a JSON body or a stream of
  server-sent events) back into OpenAI's, with the AI Protocol Manager's transcoder AI filter.

.. warning::

   The AI Protocol Manager and its transcoder are alpha, and their APIs are a work in progress: Envoy logs
   warnings about them at startup.

Step 1: Start the sandbox
*************************

Change to the ``ai-transcoder`` directory, and build and start the services.

.. code-block:: console

   $ pwd
   examples/ai-transcoder
   $ docker compose pull
   $ docker compose up --build -d
   $ docker compose ps --format "table {{.Name}}\t{{.Service}}\t{{.Ports}}"
   NAME                        SERVICE     PORTS
   ai-transcoder-anthropic-1   anthropic   8080/tcp
   ai-transcoder-gemini-1      gemini      8080/tcp
   ai-transcoder-openai-1      openai      8080/tcp
   ai-transcoder-proxy-1       proxy       0.0.0.0:9901->9901/tcp, 0.0.0.0:10000->10000/tcp

Envoy listens for AI requests on port ``10000``, and serves its admin interface on port ``9901``.

Step 2: Send the same request to each provider
**********************************************

Send an OpenAI chat completion request to Envoy, asking for a Claude model. ``created`` is set at response
time, so it is dropped for a reproducible output:

.. code-block:: console

   $ curl -s http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "In one short sentence, what is Envoy proxy?"}]}' \
       | jq 'del(.created)'
   {
     "choices": [
       {
         "finish_reason": "stop",
         "index": 0,
         "message": {
           "content": "Envoy is an open-source edge and service proxy designed for cloud-native applications.",
           "role": "assistant"
         }
       }
     ],
     "id": "msg_00000sandbox",
     "model": "claude-haiku-4-5",
     "object": "chat.completion",
     "usage": {
       "completion_tokens": 13,
       "prompt_tokens": 18,
       "total_tokens": 31
     }
   }

The Anthropic upstream answered, but the reply is an OpenAI ``chat.completion``: Envoy sent the request to
the Messages API and converted the answer, including the stop reason and the token usage.

Only the ``model`` changes between providers. Each reply carries its provider's message id:

.. code-block:: console

   $ for model in gpt-4o-mini claude-haiku-4-5 gemini-2.5-flash; do
       curl -s http://localhost:10000/v1/chat/completions \
         -H 'content-type: application/json' \
         -d "{\"model\": \"${model}\", \"messages\": [{\"role\": \"user\", \"content\": \"In one short sentence, what is Envoy proxy?\"}]}" \
         | jq -r '"\(.id) \(.model): \(.choices[0].message.content)"'
     done
   chatcmpl-00000sandbox gpt-4o-mini: Envoy is an open-source edge and service proxy designed for cloud-native applications.
   msg_00000sandbox claude-haiku-4-5: Envoy is an open-source edge and service proxy designed for cloud-native applications.
   00000sandbox gemini-2.5-flash: Envoy is an open-source edge and service proxy designed for cloud-native applications.

Step 3: Stream a response
*************************

Ask for a stream from a GPT model:

.. code-block:: console

   $ curl -sN http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "gpt-4o-mini", "stream": true, "messages": [{"role": "user", "content": "In one short sentence, what is Envoy proxy?"}]}'
   data: {"choices":[{"delta":{"content":"Envoy is an open-source edge and service proxy","role":"assistant"},"finish_reason":null,"index":0}],"created":1735689600,"id":"chatcmpl-00000sandbox","model":"gpt-4o-mini","object":"chat.completion.chunk"}

   data: {"choices":[{"delta":{"content":" designed for cloud-native applications."},"finish_reason":"stop","index":0}],"created":1735689600,"id":"chatcmpl-00000sandbox","model":"gpt-4o-mini","object":"chat.completion.chunk"}

   data: [DONE]

The other providers' streams are converted into the same OpenAI ``chat.completion.chunk`` events:
Anthropic's named events, from ``message_start`` to ``message_stop``, and Gemini's stream, which Envoy
sends to the Gemini API's ``streamGenerateContent`` method rather than ``generateContent``.

Gemini's streams just end, so Envoy also adds the ``data: [DONE]`` event that OpenAI clients wait for:

.. code-block:: console

   $ curl -sN http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "gemini-2.5-flash", "stream": true, "messages": [{"role": "user", "content": "In one short sentence, what is Envoy proxy?"}]}' \
       | grep '^data:' | tail -1
   data: [DONE]

Step 4: Ask for a model that no provider serves
***********************************************

A model that no route matches never leaves Envoy. It is answered with a ``404``, in OpenAI's error format
so that OpenAI clients can read it:

.. code-block:: console

   $ curl -s http://localhost:10000/v1/chat/completions \
       -H 'content-type: application/json' \
       -d '{"model": "llama-3.1-8b", "messages": [{"role": "user", "content": "Hi"}]}' \
       | jq
   {
     "error": {
       "message": "No backend serves this model.",
       "type": "invalid_request_error",
       "param": "model",
       "code": "model_not_found"
     }
   }

Step 5: See where each request went
***********************************

Envoy's access log shows each request's model, read from the ``envoy.ai.model.request`` filter state
object, and the cluster and path it was sent to:

.. code-block:: console

   $ docker compose logs proxy | grep -- ' -> '
   proxy-1  | claude-haiku-4-5 -> anthropic/v1/messages 200
   proxy-1  | gpt-4o-mini -> openai/v1/chat/completions 200
   proxy-1  | claude-haiku-4-5 -> anthropic/v1/messages 200
   proxy-1  | gemini-2.5-flash -> gemini/v1beta/models/gemini-2.5-flash:generateContent 200
   proxy-1  | gpt-4o-mini -> openai/v1/chat/completions 200
   proxy-1  | gemini-2.5-flash -> gemini/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse 200
   proxy-1  | llama-3.1-8b -> -/v1/chat/completions 404

Every client sent its request to ``/v1/chat/completions``. The Anthropic requests were rewritten to the
Messages API's path, and the Gemini requests show the model moved from the request body into the Gemini
API's path, with the streaming one calling ``streamGenerateContent``. The unknown model was answered by
Envoy, on no cluster.

Step 6: Check the transcoder's statistics
*****************************************

The AI Protocol Manager counts the payloads it transcoded, each request, JSON response and streamed
event, and the ones it could not. After the steps above:

.. code-block:: console

   $ curl -s "http://localhost:9901/stats?filter=ai_protocol_manager.transcoder"
   ai_protocol_manager.transcoder.failed: 0
   ai_protocol_manager.transcoder.transcoded: 31
   ai_protocol_manager.transcoder.unresolved: 0

.. seealso::

   :ref:`AI Protocol Manager <config_http_filters_ai_protocol_manager>`
      Learn more about the AI Protocol Manager filter and its AI filters.

   :ref:`Transcoder API <envoy_v3_api_msg_extensions.http.ai_filters.transcoder.v3.Transcoder>`
      The transcoder AI filter's configuration.

   :ref:`Well known filter state <well_known_filter_state>`
      Learn more about the ``envoy.ai.model.request`` filter state object.

   :ref:`Set filter state <config_http_filters_set_filter_state>`
      Learn more about the set filter state filter.
