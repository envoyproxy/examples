ARG ENVOY_IMAGE="${ENVOY_IMAGE:-envoyproxy/envoy}"
ARG ENVOY_VARIANT="${ENVOY_VARIANT:-v1.37-latest}"

# Stage 1: Build the Rust dynamic module
FROM rust:1.83-slim AS builder
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get -qq update -y \
    && apt-get -qq install --no-install-recommends -y \
        clang \
        libclang-dev \
        pkg-config \
        libssl-dev
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    --mount=type=cache,target=/build/target \
    cargo build --release \
    && cp target/release/libenvoy_dynamic_module_jq.so /libenvoy_dynamic_module_jq.so

# Stage 2: Final Envoy image with the dynamic module
FROM ${ENVOY_IMAGE}:${ENVOY_VARIANT}
ENV DEBIAN_FRONTEND=noninteractive
RUN echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get -qq update -y \
    && apt-get -qq install --no-install-recommends -y curl
COPY --from=builder --chmod=755 /libenvoy_dynamic_module_jq.so /lib/libenvoy_dynamic_module_jq.so
COPY --chmod=644 jq-libs/ /jq-libs/
COPY --chmod=644 envoy.yaml /etc/envoy.yaml
CMD ["/usr/local/bin/envoy", "-c", "/etc/envoy.yaml"]
