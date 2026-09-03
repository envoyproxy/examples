FROM envoyproxy/envoy-build:ci-v0.2.3@sha256:0fa203f090138434505a5f1269a8d2bb4a47b885facb4ef5e6dc0c9f861d2aba
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y gosu
