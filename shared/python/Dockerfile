FROM python:3.11.5-slim-bookworm@sha256:edaf703dce209d774af3ff768fc92b1e3b60261e7602126276f9ceb0e3a96874 AS python-base
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' | tee /etc/apt/apt.conf.d/keep-cache
ARG PYTHON_REQUIREMENTS_FILE=aiohttp/requirements.txt
ADD "$PYTHON_REQUIREMENTS_FILE" /tmp/requirements.txt


FROM python-base AS python-grpc-client
WORKDIR /client
RUN pip install --require-hashes -qr /tmp/requirements.txt
# Copy the sources, including the stubs
COPY --chmod=777 client.py /client/grpc-kv-client.py
COPY kv /client/kv
CMD tail -f /dev/null


FROM python-base AS aiohttp-service
ARG SERVICE_PORT=8080
ENV DEBIAN_FRONTEND=noninteractive \
    SERVICE_PORT=$SERVICE_PORT
ADD "$PYTHON_REQUIREMENTS_FILE" /tmp/requirements.txt
RUN echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    pip3 install --require-hashes -qr /tmp/requirements.txt \
    && apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends netcat-traditional \
    && mkdir /code
HEALTHCHECK \
    --interval=1s \
    --timeout=1s \
    --start-period=1s \
    --retries=3 \
    CMD nc -zv localhost "$SERVICE_PORT"
ENTRYPOINT ["python3", "/code/service.py"]


FROM aiohttp-service AS aiohttp-tracing-service
ADD tracing/service.py /code/service.py


FROM aiohttp-service AS aiohttp-tracing-service2
ADD tracing/service2.py /code/service.py


FROM aiohttp-service AS aiohttp-tracing-service3
COPY --from=envoyproxy/envoy:dev /usr/local/bin/envoy /usr/local/bin/envoy
COPY --chmod=777 tracing/start_service.sh /usr/local/bin/start_service.sh
ADD tracing/service2.py /code/service.py
ENTRYPOINT ["/usr/local/bin/start_service.sh"]


FROM aiohttp-tracing-service3 AS aiohttp-jaeger-service
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y curl
#
# for discussion on jaeger binary compatibility, and the source of the file, see here:
#  https://github.com/envoyproxy/envoy/issues/11382#issuecomment-638012072
#
RUN echo "4a7d17d4724ee890490bcd6cfdedb12a02316a3d33214348d30979abd201f1ca  /usr/local/lib/libjaegertracing_plugin.so" > /tmp/checksum \
         && curl -Ls https://github.com/envoyproxy/misc/releases/download/jaegertracing-plugin/jaegertracing-plugin-centos.tar.gz \
              | tar zxf - -C /usr/local/lib \
         && mv /usr/local/lib/libjaegertracing.so.0.4.2 /usr/local/lib/libjaegertracing_plugin.so \
         && sha256sum -c /tmp/checksum \
         && rm /tmp/checksum


FROM aiohttp-service AS aiohttp-hello-service
ADD service.py /code/service.py


FROM aiohttp-service AS aiohttp-data-service
RUN mkdir -p /code/data
RUN dd if=/dev/zero of="/code/data/file.txt" bs=1024 count=10240 \
    && dd if=/dev/zero of="/code/data/file.json" bs=1024 count=10240
ADD data-service.py /code/service.py


FROM aiohttp-service AS aiohttp-postgres-service
ADD postgres/requirements.txt /tmp/requirements.txt
RUN pip3 install -qr /tmp/requirements.txt
