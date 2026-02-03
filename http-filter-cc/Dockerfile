FROM envoyproxy/envoy-build:ci-cdfbb76bc18c115270127132c6f7c67000cd2e74@sha256:48a8b1bc24ed771560126642dcbba33c50c6b837722ba9c75270b858ef7ab3a6 AS builder

WORKDIR /build
COPY --chmod=755 . /build
RUN bazel build --experimental_repository_downloader_retries=2 //:envoy


FROM envoyproxy/envoy:dev

COPY --from=builder /build/bazel-bin/envoy /usr/local/bin/envoy
COPY envoy.yaml /etc/envoy/envoy.yaml
CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy/envoy.yaml"]
