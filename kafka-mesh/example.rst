.. _install_sandboxes_kafka_mesh:

Kafka mesh filter
=================

.. sidebar:: Requirements

   .. include:: _include/docker-env-setup-link.rst

   :ref:`curl <start_sandboxes_setup_curl>`
        Used to make HTTP requests.

This example demonstrates the Kafka mesh filter, which routes Kafka traffic 
to different upstream clusters based on topic name.

The :ref:`Kafka broker filter <install_sandboxes_kafka>` passes all traffic 
to a single upstream Kafka cluster while collecting metrics. The mesh filter 
goes further: it reads the Kafka protocol, extracts the topic name from each 
request, and forwards it to the appropriate upstream cluster.

In this example we configure two upstream Kafka clusters with routing rules:

- Topics starting with ``a`` (e.g., ``apples``) → **cluster1**
- Topics starting with ``b`` (e.g., ``bananas``) → **cluster2**

Clients connect to Envoy as if it were a single Kafka broker. Envoy handles 
the routing transparently.


Step 1: Start all containers
****************************

Change to the ``kafka-mesh`` directory and start the containers. This brings 
up Envoy, two independent Kafka clusters, and a shared Zookeeper instance.

.. code-block:: console

   $ pwd
   envoy/examples/kafka-mesh
   $ docker compose pull
   $ docker compose up --build -d
   $ docker compose ps

         Name                       State              Ports
   ------------------------------------------------------------------
   kafka-mesh_proxy_1          Up             0.0.0.0:10000->10000/tcp
   kafka-mesh_kafka-cluster1_1 Up             9092/tcp
   kafka-mesh_kafka-cluster2_1 Up             9092/tcp
   kafka-mesh_zookeeper_1      Up (healthy)   2181/tcp


Step 2: Produce a message to the ``apples`` topic
*************************************************

Send a message to a topic starting with ``a``. The mesh filter will route 
this to **cluster1**.

.. code-block:: console

   $ docker compose run --rm kafka-client \
       /bin/bash -c "echo 'hello from apples' | kafka-console-producer --request-required-acks 1 --producer-property enable.idempotence=false --broker-list proxy:10000 --topic apples"


Step 3: Produce a message to the ``bananas`` topic
**************************************************

Send a message to a topic starting with ``b``. The mesh filter will route 
this to **cluster2**.

.. code-block:: console

   $ docker compose run --rm kafka-client \
       /bin/bash -c "echo 'hello from bananas' | kafka-console-producer --request-required-acks 1 --producer-property enable.idempotence=false --broker-list proxy:10000 --topic bananas"


Step 4: Verify the message landed in cluster1
*********************************************

To confirm the routing worked, consume directly from **cluster1** (bypassing 
Envoy). You should see the ``apples`` message:

.. code-block:: console

   $ docker compose run --rm kafka-client \
       kafka-console-consumer --bootstrap-server kafka-cluster1:9092 --topic apples --from-beginning --max-messages 1
   hello from apples

The ``bananas`` topic should not exist on cluster1.


Step 5: Verify the message landed in cluster2
*********************************************

Similarly, consume directly from **cluster2**. You should see the ``bananas`` 
message:

.. code-block:: console

   $ docker compose run --rm kafka-client \
       kafka-console-consumer --bootstrap-server kafka-cluster2:9092 --topic bananas --from-beginning --max-messages 1
   hello from bananas

The ``apples`` topic should not exist on cluster2.


Step 6: Consume through the mesh filter
***************************************

The mesh filter also routes fetch (consume) requests to the correct upstream. 
Clients can consume through Envoy without knowing which cluster holds the data.

.. note::

   The mesh filter supports only Produce and Fetch Kafka APIs. Consumer group 
   coordination (FIND_COORDINATOR, etc.) is not supported, so we disable the 
   consumer group by setting ``group.id=`` (empty string).

Consume the ``apples`` topic through Envoy:

.. code-block:: console

   $ docker compose run --rm kafka-client \
       kafka-console-consumer --bootstrap-server proxy:10000 --topic apples --from-beginning --max-messages 1 --consumer-property group.id=
   hello from apples

Consume the ``bananas`` topic through Envoy:

.. code-block:: console

   $ docker compose run --rm kafka-client \
       kafka-console-consumer --bootstrap-server proxy:10000 --topic bananas --from-beginning --max-messages 1 --consumer-property group.id=
   hello from bananas


Step 7: Check Envoy stats
*************************

Envoy records metrics for Kafka traffic. Query the admin interface to see 
produce and fetch request counts:

.. code-block:: console

   $ curl -s "http://localhost:8001/stats?filter=kafka" | grep -v ": 0" | grep "_request:"
   kafka.kafka_mesh.request.produce_request: 2
   kafka.kafka_mesh.request.fetch_request: 4
   kafka.kafka_mesh.request.metadata_request: 8


.. seealso::

   :ref:`Envoy Kafka mesh filter <config_network_filters_kafka_mesh>`
     Learn more about the Kafka mesh filter configuration.

   :ref:`Kafka broker filter example <install_sandboxes_kafka>`
     A simpler example using the broker filter for single-cluster proxying.
