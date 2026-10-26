FROM envoyproxy/envoy-build:ci-v0.2.5@sha256:8fdf16ea0d40cb0e4726b13f97df8b73e80e331b206b62b224ceb2498149a1d5
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y gosu
