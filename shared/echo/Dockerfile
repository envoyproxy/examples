FROM debian:trixie-slim

ARG BINS_VERSION=0.1.47
ARG ECHO_VERSION=0.1.0
ARG TARGETARCH

RUN --mount=type=tmpfs,target=/var/cache/apt \
    --mount=type=tmpfs,target=/var/lib/apt/lists \
    apt-get -qq update \
    && apt-get -qq install -y libssl-dev ca-certificates curl

RUN curl -fsSL "https://github.com/envoyproxy/toolshed/releases/download/bins-v${BINS_VERSION}/echo-${ECHO_VERSION}-${TARGETARCH}" \
         -o /usr/local/bin/example-echo \
    && chmod +x /usr/local/bin/example-echo
EXPOSE 8080
COPY <<EOF /etc/config.yaml
listeners:
  http:
    port: 8080
    host: >-
      0.0.0.0

EOF
COPY ./snakeoil /tmp/snakeoil
CMD ["example-echo", "-c", "/etc/config.yaml"]
