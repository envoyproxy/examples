FROM debian:trixie-slim

ARG BINS_VERSION=0.1.47
ARG ECHO_VERSION=0.1.0
ARG TARGETARCH

RUN --mount=type=tmpfs,target=/var/cache/apt \
    --mount=type=tmpfs,target=/var/lib/apt/lists \
    apt-get -qq update \
    && apt-get -qq install -y libssl-dev ca-certificates curl

# Download pre-built binary from toolshed releases
# Note: Checksums are not currently published for these binaries
RUN test -n "${TARGETARCH}" || (echo "Error: TARGETARCH build arg must be set" && exit 1) \
    && curl -fsSL "https://github.com/envoyproxy/toolshed/releases/download/bins-v${BINS_VERSION}/echo-${ECHO_VERSION}-${TARGETARCH}" \
         -o /usr/local/bin/example-echo \
    && chmod +x /usr/local/bin/example-echo \
    && apt-get -qq remove --purge -y curl \
    && apt-get -qq autoremove -y
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
