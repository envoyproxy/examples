FROM envoyproxy/envoy-build:ci-cdfbb76bc18c115270127132c6f7c67000cd2e74@sha256:48a8b1bc24ed771560126642dcbba33c50c6b837722ba9c75270b858ef7ab3a6 AS builder
ARG USER_ID
ENV USER_ID="${USER_ID:-1000}"
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -qq update \
    && apt-get -qq install --no-install-recommends -y gettext-base \
    && usermod -u "$USER_ID" envoybuild \
    && mkdir -p /home/envoybuild/.cache/bazel
WORKDIR /build
COPY --chmod=755 --chown=envoybuild . /build
RUN chown envoybuild /build && chown -R envoybuild:envoybuild /home/envoybuild/.cache
USER envoybuild
ARG GITHUB_TOKEN
ENV GITHUB_TOKEN="${GITHUB_TOKEN:-}"
ARG ENVOY_BZLMOD_COMMIT
ENV ENVOY_BZLMOD_COMMIT="${ENVOY_BZLMOD_COMMIT:-}"
ARG ENVOY_BZLMOD_REGISTRY
ENV ENVOY_BZLMOD_REGISTRY="${ENVOY_BZLMOD_REGISTRY:-}"
RUN --mount=type=cache,target=/home/envoybuild/.cache/bazel,sharing=locked,uid="${USER_ID}" \
    envsubst '${ENVOY_BZLMOD_COMMIT}' < MODULE.bazel.tpl > MODULE.bazel \
    && envsubst '${ENVOY_BZLMOD_REGISTRY}' < registry.bazelrc.tpl > registry.bazelrc \
    && bazel --version \
    && bazel build --config=clang //:envoy \
    && mkdir out \
    && cp -a bazel-bin/envoy out/


FROM envoyproxy/envoy:dev
COPY --from=builder /build/out/envoy /usr/local/bin/envoy
COPY envoy.yaml /etc/envoy/envoy.yaml
CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy/envoy.yaml"]
