FROM debian:trixie-slim
ARG BINS_VERSION=0.1.47
ARG ECHO_VERSION=0.1.0
ARG ECHO_SHA256_amd64=da08855d7d5357630aba2da044467773b7e4de806204ea984dc2d11782032885
ARG ECHO_SHA256_arm64=4fe0bbbeeec8b03c3b7bc9d70815153fe5651494c8d63220b33f66d75674ddc9
ARG TARGETARCH
RUN --mount=type=tmpfs,target=/var/cache/apt \
    --mount=type=tmpfs,target=/var/lib/apt/lists \
    apt-get -qq update \
    && apt-get -qq install -y libssl-dev ca-certificates curl \
    && test -n "${TARGETARCH}" || (echo "Error: TARGETARCH build arg must be set" && exit 1) \
    && curl -fsSL "https://github.com/envoyproxy/toolshed/releases/download/bins-v${BINS_VERSION}/echo-${ECHO_VERSION}-${TARGETARCH}" \
         -o /usr/local/bin/example-echo \
    && case "${TARGETARCH}" in \
         amd64) EXPECTED_SHA="${ECHO_SHA256_amd64}" ;; \
         arm64) EXPECTED_SHA="${ECHO_SHA256_arm64}" ;; \
         *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
       esac \
    && echo "${EXPECTED_SHA}  /usr/local/bin/example-echo" | sha256sum -c - \
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
