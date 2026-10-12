FROM envoyproxy/envoy-build:ci-v0.2.4@sha256:0ec8c3295229234f5a5663b858d9e217fd409e2eba22afe7a9c6e4f634bd7ea8
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y gosu
